import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class DocumentationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        (self.root/'docs').mkdir()
        self.patch=patch.object(server,'ROOT',self.root)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def doc(self,name,content):
        path=self.root/'docs'/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(content,encoding='utf-8')
        return path

    def test_only_boolean_true_is_published(self):
        self.doc('plain.md','# Private')
        self.doc('draft.md','---\npublished: false\n---\nPRIVATE')
        self.doc('string.md','---\npublished: "true"\n---\nPRIVATE')
        self.doc('number.md','---\npublished: 1\n---\nPRIVATE')
        self.doc('public.md','---\npublished: true\n---\n# Public\nBODY')
        result=server.documentation({})
        self.assertEqual([item['path'] for item in result['items']],['public.md'])
        self.assertNotIn('content',result['items'][0])
        for path in ['plain.md','draft.md','string.md','number.md','../studio/server.py']:
            with self.assertRaises(KeyError):server.documentation({'path':[path]})

    def test_nested_metadata_and_sorting(self):
        self.doc('folder/b.md','---\npublished: true\ntitle: 第二篇\ncategory: 指南\norder: 20\n---\n# B')
        self.doc('a.md','---\npublished: true\norder: 10\n---\n# A')
        docs=server.documentation({})['items']
        self.assertEqual([d['path'] for d in docs],['a.md','folder/b.md'])
        detail=server.documentation({'path':['folder/b.md']})
        self.assertEqual(detail['title'],'第二篇')
        self.assertEqual(detail['content'],'# B')

    def test_revoke_and_body_updates_are_immediate(self):
        path=self.doc('a.md','---\npublished: true\n---\nFirst')
        self.assertEqual(server.documentation({'path':['a.md']})['content'],'First')
        path.write_text('---\npublished: true\n---\nSecond')
        self.assertEqual(server.documentation({'path':['a.md']})['content'],'Second')
        path.write_text('---\npublished: false\n---\nSecond')
        self.assertEqual(server.documentation({})['items'],[])
        with self.assertRaises(KeyError):server.documentation({'path':['a.md']})

    def test_bad_frontmatter_fails_closed(self):
        for i,header in enumerate(['published: true\npublished: false','published: [true','published: true\norder: !!python/object:bad {}','published: true\n---no-close']):
            self.doc(f'bad{i}.md',f'---\n{header}\n---\nPRIVATE')
        self.assertEqual(server.documentation({})['items'],[])

    def test_symlink_outside_docs_not_read(self):
        external=self.root/'private.md'
        external.write_text('---\npublished: true\n---\nSECRET')
        (self.root/'docs'/'outside.md').symlink_to(external)
        self.assertEqual(server.documentation({})['items'],[])

    def test_invalid_root_and_oversized_docs_not_published(self):
        self.doc('big.md','---\npublished: true\n---\n'+'a'*(1024*1024))
        self.assertEqual(server.documentation({})['items'],[])

if __name__=='__main__':unittest.main()
