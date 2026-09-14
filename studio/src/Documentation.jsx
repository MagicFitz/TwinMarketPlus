import React, { useEffect, useState } from 'react';
import { Button, Card, Input, Icon, Tag, CodeBlock } from 'animal-island-ui';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Unlike monitoring snapshots, revoked or unverifiable documents must not stay visible.
function usePublished(url, refresh) {
  const [state, setState] = useState({url:null,data:null,loading:true,error:null});
  useEffect(() => {
    let active=true, pending=false;
    const abort=new AbortController();
    setState(previous=>({...previous,url,data:previous.url===url?previous.data:null,loading:!!url,error:null}));
    async function read() {
      if(!url || pending)return;
      pending=true;
      try {
        const response=await fetch(url,{signal:abort.signal});
        if(!response.ok)throw Error(response.status===404?'文档未发布或已撤回':'无法确认文档发布状态');
        const data=await response.json();
        if(active)setState({url,data,loading:false,error:null});
      } catch(error) {
        if(active&&error.name!=='AbortError')setState({url,data:null,loading:false,error:error.message});
      } finally {pending=false;}
    }
    read();const timer=setInterval(read,5000);
    return()=>{active=false;abort.abort();clearInterval(timer);};
  },[url,refresh]);
  return state.url!==url?{data:null,loading:!!url,error:null}:state;
}

export function Documentation({refresh}) {
  const [query,setQuery]=useState('');
  const [requested,setRequested]=useState(()=>new URLSearchParams(location.search).get('doc'));
  const [manual,setManual]=useState(0);
  const catalog=usePublished('/api/documentation',`${refresh}:${manual}`);
  const items=catalog.data?.items || [];
  const selected=requested ?? items[0]?.path;
  const entry=items.find(item=>item.path===selected);
  const article=usePublished(entry?`/api/documentation?path=${encodeURIComponent(entry.path)}`:null,`${refresh}:${manual}`);
  useEffect(()=>{const pop=()=>setRequested(new URLSearchParams(location.search).get('doc'));window.addEventListener('popstate',pop);return()=>window.removeEventListener('popstate',pop);},[]);
  function select(path, hash='') {
    history.pushState({},'',`/studio/Documentation?doc=${encodeURIComponent(path)}${hash}`);
    setRequested(path);
    if(!hash)window.scrollTo(0,0);
  }
  function documentLink({href,children}) {
    if(!href)return <span>{children}</span>;
    if(href.startsWith('#'))return <a href={href}>{children}</a>;
    if(/^https?:\/\//i.test(href))return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
    let target, path;
    try {target=new URL(href,`https://docs.invalid/${selected || ''}`);path=decodeURIComponent(target.pathname.slice(1));}
    catch {return <span>{children}</span>;}
    if(target.origin!=='https://docs.invalid' || !items.some(item=>item.path===path))return <span className="unavailable-link">{children}</span>;
    return <a href={`/studio/Documentation?doc=${encodeURIComponent(path)}${target.hash}`} onClick={e=>{if(e.metaKey||e.ctrlKey)return;e.preventDefault();select(path,target.hash);}}>{children}</a>;
  }
  const matches=items.filter(item=>`${item.title} ${item.category}`.toLowerCase().includes(query.toLowerCase()));
  return <>
    <div className="page-heading"><h1>文档</h1><Button type="primary" onClick={()=>setManual(n=>n+1)} icon={<Icon name="Refresh" size={18}/>}>刷新文档</Button></div>
    <div className="docs-layout">
      <Card className="docs-index">
        <Input size="small" aria-label="搜索文档" placeholder="搜索文档" value={query} onChange={e=>setQuery(e.target.value)} prefix={<Icon name="Search" size={16}/>}/>
        <nav aria-label="文档列表">{matches.map(item=><a key={item.path} href={`/studio/Documentation?doc=${encodeURIComponent(item.path)}`} aria-current={item.path===selected?'page':undefined} onClick={e=>{if(e.metaKey||e.ctrlKey)return;e.preventDefault();select(item.path);}}><span>{item.title}</span><small>{item.category}</small></a>)}</nav>
        {!matches.length&&<p className="empty">{catalog.loading?'读取中…':catalog.error || (query?'无匹配文档':'暂无已发布文档')}</p>}
      </Card>
      <Card className="docs-reader">
        {entry&&article.data?<>
          <header className="doc-heading"><Tag variant="soft" size="small">{entry.category}</Tag><h2>{article.data.title}</h2></header>
          <article className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={{
            a:documentLink,
            img:({alt})=><span className="image-description">[图片：{alt || '未命名'}]</span>,
            pre:({children})=><CodeBlock code={String(React.Children.toArray(children)[0]?.props?.children || '').replace(/\n$/,'')}/>,
            table:({children})=><div className="table-wrap"><table>{children}</table></div>,
          }}>{article.data.content.replace(/^#\s+[^\n]+\n/,'')}</ReactMarkdown></article>
          <div className="doc-source">docs/{entry.path}</div>
        </>:<div className="empty" role="status">{catalog.error || article.error || (catalog.loading || (entry&&article.loading)?'读取中…':requested?'文档未发布或已撤回':'暂无已发布文档')}</div>}
      </Card>
    </div>
  </>;
}
