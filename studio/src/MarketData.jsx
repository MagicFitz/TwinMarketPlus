import React, { useEffect, useState } from 'react';
import { Button, Card, Checkbox, Drawer, Input, Select, Switch, Tag } from 'animal-island-ui';
import './market-data.css';

export async function marketRequest(path, body, method = 'POST') {
  const response = await fetch(path, body === undefined ? { method } : {
    method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '市场数据请求失败');
  return data;
}

function useMarketResource(path, interval = 0) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [revision, refresh] = useState(0);
  useEffect(() => {
    let alive = true, pending = false;
    const controller = new AbortController();
    async function read() {
      if (pending) return;
      pending = true;
      try {
        const response = await fetch(path, { signal: controller.signal });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || '市场数据读取失败');
        if (alive) { setData(result); setError(''); }
      } catch (reason) { if (alive && reason.name !== 'AbortError') setError(reason.message); }
      finally { pending = false; }
    }
    read();
    const timer = interval ? setInterval(read, interval) : null;
    return () => { alive = false; controller.abort(); clearInterval(timer); };
  }, [path, interval, revision]);
  return { data, error, refresh: () => refresh(value => value + 1) };
}

const statusText = {
  unconfigured: '未配置', untested: '尚未测试', available: '可用', partial: '部分权限', failed: '失败',
  permission_denied: '无权限', rate_limited: '限流', missing: '缺失', ready: '可用', ready_with_warnings: '可用 · 有警告',
  queued: '排队中', running: '同步中', completed: '已完成', cancelled: '已取消',
};
const phases = { queued: '排队', calendar: '交易日历', fetching: '拉取行情', aggregating: '聚合指数', validating: '质量校验',
  publishing: '发布快照', completed: '发布完成', failed: '失败', cancelled: '已取消', rate_limit_wait: '限流等待', retry_wait: '重试等待' };
const datasets = { daily: '日线行情', trade_cal: '交易日历', daily_basic: '每日估值', moneyflow: '资金流', news: '新闻' };
const stamp = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '尚未测试';
const Status = ({ value }) => <Tag size="small" variant="soft" color={['failed', 'permission_denied', 'missing'].includes(value) ? 'orange' : 'green'}>{statusText[value] || value}</Tag>;

export function TushareConnection() {
  const resource = useMarketResource('/api/settings/data-sources');
  const source = resource.data?.items?.[0];
  const [token, setToken] = useState(''), [busy, setBusy] = useState(''), [message, setMessage] = useState(''), [error, setError] = useState('');
  async function act(kind, body) {
    setBusy(kind); setError(''); setMessage('');
    try {
      if (kind === 'test') await marketRequest('/api/settings/data-sources/tushare/test');
      else await marketRequest('/api/settings/data-sources/tushare', body, 'PUT');
      setToken(''); resource.refresh();
      setMessage(kind === 'test' ? '权限测试已完成，请查看各接口状态。' : '数据源设置已保存。');
    } catch (reason) { setError(reason.message); }
    finally { setBusy(''); }
  }
  return <div className="market-data">
    <div className="market-data-heading"><div><h3>Tushare Pro</h3><p>收盘后日级数据 · 固定官方服务地址</p></div><Status value={source?.status || 'unconfigured'} /></div>
    {source && <div className="market-data-heading"><span>{source.token_configured ? `Token 已配置 · ${source.credential_source === 'environment' ? '环境变量优先' : '本地保密配置'}` : '尚未配置 Token'}</span><Switch checked={source.enabled} disabled={!!busy} onChange={enabled => act('save', { enabled })} checkedChildren="启用" unCheckedChildren="停用" /></div>}
    <form onSubmit={event => { event.preventDefault(); act('save', token.trim() ? { token } : {}); }}>
      <label className="market-field"><span>新增或替换 Token</span><Input type="password" autoComplete="new-password" value={token} onChange={event => setToken(event.target.value)} placeholder="留空保留现有 Token" disabled={!!busy || !source} /></label>
      <div className="market-data-actions"><Button htmlType="submit" type="primary" disabled={!!busy || !source} loading={busy === 'save'}>保存连接</Button><Button onClick={() => act('test')} disabled={!!busy || !source?.token_configured || !source?.enabled} loading={busy === 'test'}>测试连接</Button><Button type="text" disabled={!!busy || !source?.token_configured || source?.credential_source === 'environment'} onClick={() => act('clear', { token: '' })}>清除本地 Token</Button></div>
    </form>
    <div className="market-capabilities">{Object.entries(datasets).filter(([key]) => ['daily', 'trade_cal', 'daily_basic'].includes(key)).map(([key, name]) => <div key={key}><span>{name}</span><Status value={source?.capabilities?.[key]?.status || 'untested'} /><small>{source?.capabilities?.[key]?.message}</small></div>)}</div>
    <p className="market-muted">最近测试：{stamp(source?.last_tested_at)}。新闻、资金流和盘中预览将在后续接入。</p>
    {(error || resource.error) && <p className="runtime-error" role="alert">{error || resource.error}</p>}
    {message && <p role="status">{message}</p>}
  </div>;
}

function SnapshotDetails({ snapshot }) {
  return <div className="market-data">
    <dl className="market-facts"><div><dt>快照</dt><dd>{snapshot.snapshot_id}</dd></div><div><dt>覆盖日期</dt><dd>{snapshot.start_date} 至 {snapshot.effective_through}</dd></div><div><dt>转换规则</dt><dd>{snapshot.transform_version}</dd></div><div><dt>最小有效成分权重</dt><dd>{(snapshot.quality.minimum_weight_coverage * 100).toFixed(2)}%</dd></div><div><dt>估值空值</dt><dd>{snapshot.quality.valuation_missing_values}</dd></div></dl>
    <h3>数据能力</h3><div className="market-capabilities">{Object.entries(snapshot.datasets).map(([key, value]) => <div key={key}><span>{datasets[key] || key}</span><Status value={value.status} /></div>)}</div>
    <h3>质量报告</h3><ul className="market-warning-list">{snapshot.quality.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
    <h3>资产定义 SHA-256</h3><p className="market-fingerprint">{snapshot.asset_definition_sha256}</p>
    <h3>文件指纹</h3><div className="market-file-list">{Object.entries(snapshot.files).map(([name, file]) => <article key={name}><strong>{name}</strong><small>{file.bytes.toLocaleString()} bytes</small><p className="market-fingerprint">{file.sha256}</p></article>)}</div>
  </div>;
}

export function MarketWorkbench() {
  const resource = useMarketResource('/api/market/overview', 3000);
  const data = resource.data;
  const [open, setOpen] = useState(false), [detail, setDetail] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [form, setForm] = useState({ mode: 'incremental', start_date: '', end_date: '', daily_basic: true, allow_missing_news: false });
  const change = (key, value) => setForm(previous => ({ ...previous, [key]: value }));
  const active = data?.active_snapshot;
  const ongoing = data?.jobs.some(job => ['queued', 'running'].includes(job.status));
  function showSync() {
    setError('');
    setForm(previous => ({ ...previous, start_date: data?.suggested_start_date || '', end_date: data?.latest_closed_date || '' }));
    setOpen(true);
  }
  async function sync(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      await marketRequest('/api/market/sync-jobs', { ...form, datasets: ['trade_cal', 'daily', ...(form.daily_basic ? ['daily_basic'] : [])] });
      setOpen(false); resource.refresh();
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }
  async function act(path) {
    setBusy(true); setError('');
    try { await marketRequest(path); resource.refresh(); }
    catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }
  if (!data) return <Card className="panel"><p role={resource.error ? 'alert' : 'status'}>{resource.error || '正在读取市场数据工作台…'}</p><Button onClick={resource.refresh}>刷新</Button></Card>;
  return <div className="market-data">
    <Card className="panel"><div className="market-data-heading"><div><h2>市场数据工作台</h2><p>收盘后日级快照 · 本地可复现市场环境</p></div><Button type="primary" disabled={busy || ongoing || !data.source.token_configured || !data.source.enabled} onClick={showSync}>更新数据</Button></div>
      {!data.source.token_configured && <p className="market-notice">请先前往 <a href="/studio/Setting#sources">Setting 配置 Tushare 连接</a>。</p>}
      <dl className="market-facts"><div><dt>新实验默认快照</dt><dd>{active?.snapshot_id || '内置历史文件'}</dd></div><div><dt>有效截至</dt><dd>{active?.effective_through || data.baseline_through || '未知'}</dd></div><div><dt>质量状态</dt><dd>{active ? <Status value={active.status} /> : '尚未发布快照'}</dd></div><div><dt>本地行情已同步至</dt><dd>{data.baseline_through}</dd></div></dl>
      {active && <div className="market-capabilities">{Object.entries(active.datasets).map(([key, value]) => <div key={key}><span>{datasets[key] || key}</span><Status value={value.status} /></div>)}</div>}
      <p className="market-muted">同步完成后手动设为默认。已有实验继续使用创建时固定的快照。</p>
    </Card>
    {(error || resource.error) && <p className="runtime-error" role="alert">{error || resource.error}</p>}
    <Card className="panel"><div className="market-data-heading"><h2>同步任务</h2><Button size="small" onClick={resource.refresh}>刷新</Button></div>
      {data.jobs.length ? <div className="market-jobs">{data.jobs.map(job => <article key={job.job_id}><div className="market-data-heading"><div><strong>{phases[job.stage] || job.stage}</strong><p>{job.request.start_date} 至 {job.request.end_date}</p></div><Status value={job.status} /></div><progress aria-label={`${job.job_id} 同步进度`} value={job.progress} max="1" /><div className="market-data-heading"><small>{Math.round(job.progress * 100)}% · {stamp(job.created_at)}</small>{['queued', 'running'].includes(job.status) && <Button size="small" disabled={busy || job.cancel_requested} onClick={() => act(`/api/market/sync-jobs/${job.job_id}/cancel`)}>{job.cancel_requested ? '等待安全取消' : '取消任务'}</Button>}</div>{job.error && <p role="alert">{job.error} · {job.error_code}</p>}{job.snapshot_id && <small>{job.snapshot_id}</small>}</article>)}</div> : <p className="market-muted">暂无同步任务。任务状态保存在本地，刷新页面后可以继续查看。</p>}
    </Card>
    <Card className="panel"><h2>不可变环境快照</h2><div className="table-wrap"><table><thead><tr><th>快照</th><th>覆盖范围</th><th>状态</th><th>操作</th></tr></thead><tbody>{data.snapshots.map(snapshot => <tr key={snapshot.snapshot_id}><td><strong>{snapshot.snapshot_id}</strong><p>{snapshot.active ? '新实验默认' : snapshot.transform_version}</p></td><td>{snapshot.start_date}<br />{snapshot.effective_through}</td><td><Status value={snapshot.status} /></td><td><div className="market-data-actions"><Button size="small" onClick={() => setDetail(snapshot)}>质量与指纹</Button><Button size="small" disabled={busy || snapshot.active} onClick={() => act(`/api/market/snapshots/${snapshot.snapshot_id}/activate`)}>{snapshot.active ? '当前默认' : '设为新实验默认'}</Button></div></td></tr>)}</tbody></table></div>{!data.snapshots.length && <p className="market-muted">首次同步后将在这里展示快照及质量报告。</p>}</Card>
    <Card className="panel"><h2>资产成分与权重</h2><p className="market-muted">保留 10 个自定义指数。旧描述中的百分比舍入误差已按比例归一，并记录在资产定义中。</p><div className="market-assets">{Object.entries(data.assets.assets).map(([code, asset]) => <details key={code}><summary>{code} · {asset.name} · {asset.constituents.length} 只成分股</summary><div className="table-wrap"><table><thead><tr><th>成分股</th><th>代码</th><th>权重</th></tr></thead><tbody>{asset.constituents.map(c => <tr key={c.ts_code}><td>{c.name}</td><td>{c.ts_code}</td><td>{(c.weight * 100).toFixed(2)}%</td></tr>)}</tbody></table></div></details>)}</div></Card>
    <Drawer open={open} title="同步收盘后行情" onClose={() => !busy && setOpen(false)} pushBackground={false} width="min(560px,100vw)"><form className="market-sync-form market-data" onSubmit={sync}>
      <label className="market-field"><span>同步方式</span><Select value={form.mode} onChange={value => change('mode', value)} options={[{ key: 'incremental', label: '增量更新 · 重拉最近 3 个交易日' }, { key: 'backfill', label: '指定日期回补' }]} /></label>
      {form.mode === 'backfill' && <label className="market-field"><span>起始日期</span><Input type="date" required value={form.start_date} max={form.end_date} onChange={event => change('start_date', event.target.value)} /></label>}
      <label className="market-field"><span>结束日期</span><Input type="date" required value={form.end_date} max={data.latest_closed_date} onChange={event => change('end_date', event.target.value)} /></label>
      <p>交易日历、50 只成分股日线必选；每个交易日拉取全市场截面，再生成 10 个自定义指数。</p>
      <Checkbox value={form.daily_basic ? ['daily_basic'] : []} onChange={values => change('daily_basic', values.includes('daily_basic'))} options={[{ value: 'daily_basic', label: '每日估值 · 无权限时保留空值' }]} />
      <p className="market-notice">本期未接入新闻和资金流。新闻容器为空，新闻检索停用；这项研究限制会写入 Run 清单。</p>
      <Checkbox value={form.allow_missing_news ? ['allow'] : []} onChange={values => change('allow_missing_news', values.includes('allow'))} options={[{ value: 'allow', label: '明确允许无新闻模式' }]} />
      <p className="market-muted">增量起始参考：{data.suggested_start_date}。调用量约为区间交易日数 × {form.daily_basic ? '2' : '1'} 个行情接口，另加交易日历；分页和重试会增加调用量。</p>
      {error && <p className="runtime-error" role="alert">{error}</p>}<Button htmlType="submit" type="primary" loading={busy} disabled={busy || !form.allow_missing_news}>创建同步任务</Button>
    </form></Drawer>
    <Drawer open={!!detail} title="快照质量与文件指纹" onClose={() => setDetail(null)} width="min(640px,100vw)" pushBackground={false}>{detail && <SnapshotDetails snapshot={detail} />}</Drawer>
  </div>;
}

export function RunMarketSnapshot({ value, onChange, startDate, endDate, allowMissingNews, onAllowMissingNews, onValidity }) {
  const resource = useMarketResource('/api/market/snapshots');
  const snapshots = resource.data?.items || [];
  const selected = snapshots.find(item => item.snapshot_id === value);
  useEffect(() => {
    if (value !== undefined || !resource.data) return;
    onChange(snapshots.find(item => item.active)?.snapshot_id || '');
  }, [resource.data, value, onChange]);
  const rangeValid = !value || !!selected && startDate >= selected.earliest_run_date && endDate <= selected.effective_through;
  const newsValid = !selected || selected.datasets.news.status !== 'missing' || allowMissingNews;
  const valid = !!resource.data && value !== undefined && rangeValid && newsValid;
  useEffect(() => { onValidity(valid); }, [valid, onValidity]);
  return <section className="market-data run-market-snapshot">
    <label className="market-field"><span>市场环境快照</span><Select value={value || ''} onChange={onChange} disabled={!resource.data} options={[{ key: '', label: '内置历史文件 · 旧版数据模式' }, ...snapshots.map(item => ({ key: item.snapshot_id, label: `${item.active ? '默认 · ' : ''}${item.snapshot_id}` }))]} /></label>
    {resource.error && <p className="runtime-error" role="alert">{resource.error}<Button size="small" onClick={resource.refresh}>重试</Button></p>}
    {selected && <><p>行情有效截至 {selected.effective_through} · {selected.transform_version} · 资产定义 v{selected.asset_definition_version}</p><div className="market-capabilities">{Object.entries(selected.datasets).map(([key, data]) => <div key={key}><span>{datasets[key] || key}</span><Status value={data.status} /></div>)}</div><p className="market-notice">行情已更新，新闻缺失。无新闻环境不会使用旧新闻索引。</p><Checkbox value={allowMissingNews ? ['allow'] : []} onChange={values => onAllowMissingNews(values.includes('allow'))} options={[{ value: 'allow', label: '允许此实验使用无新闻环境' }]} /></>}
    {!rangeValid && <p className="runtime-error" role="alert">快照未覆盖所选日期。<a href="/studio/Market">前往 Market 更新数据</a>，或调整模拟日期。</p>}
  </section>;
}
