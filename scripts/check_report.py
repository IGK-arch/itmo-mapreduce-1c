"""Evidence, arithmetic, screenshot provenance and final PDF layout checks."""
import hashlib
import json
import re

import bootstrap
from bootstrap import ROOT
import pymupdf


def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))


def main():
    verification=read('evidence/verification.json')
    assert verification['all_equal'] and verification['mapper_failure_recovered']
    assert verification['selected_vacancies']==18165
    runs=read('evidence/benchmark-runs.json')
    assert len(runs)==9
    for method in ('baseline','optimized','duckdb'):
        subset=[r for r in runs if r['method']==method]
        assert len(subset)==3 and {r['trial'] for r in subset}=={1,2,3}
        assert all(r['exit_code']==0 and r['peak_process_tree_rss_bytes']>0 for r in subset)
    assert read('evidence/analysis-validation.json')['all_checks_passed']
    pdf=pymupdf.open(ROOT/'output'/'pdf'/'Карташов_Игорь_J3312_MapReduce.pdf')
    assert len(pdf)==10
    for i,page in enumerate(pdf):
        assert len(page.get_text())>200
        for block in page.get_text('blocks'):
            assert block[0]>=18 and block[2]<=page.rect.width-18,(i+1,block[:4])
            assert block[1]>=15 and block[3]<=page.rect.height-15,(i+1,block[:4])
    text='\n'.join(page.get_text() for page in pdf)
    repository=read('evidence/repository.json')['url']
    assert any(link.get('uri')==repository for page in pdf for link in page.get_links())
    for token in ['ОТЧЁТ ПО ЛАБОРАТОРНОЙ РАБОТЕ 3','18 165','229 388','632 504','174 615','7 594','270 000','259 500','137 500','200 000','175 000','150 000']:
        assert token in text,token
    assert 'приложены в ZIP' not in text and 'полные журналы приложены' not in text
    images={hashlib.sha256(pdf.extract_image(image[0])['image']).hexdigest()
            for page in pdf for image in page.get_images(full=True)}
    expected={hashlib.sha256((ROOT/'evidence'/'screenshots'/name).read_bytes()).hexdigest()
              for name in ['raw-objects.jpg','mapreduce-results.jpg']}
    assert images==expected and len(images)==2
    views=read('evidence/pdf-image-views.json')
    assert len(views)==4
    for i,view in enumerate(views):
        x,y,w,h=view['source_box'];iw,ih=view['source_size']
        assert x>=0 and y>=0 and x+w<=iw and y+h<=ih
        assert view['scale']>=0.5
        px,py,ex,ey=view['page_box']
        assert 18<=px<ex<=A4_WIDTH-18
        assert 18<=py<ey<=A4_HEIGHT-18
        for other in views[:i]:
            if view['source']==other['source']:
                a,b,c,d=other['source_box']
                assert min(x+w,a+c)<=max(x,a) or min(y+h,b+d)<=max(y,b)
    result={'passed':True,'pages':len(pdf),'unique_screenshots':2,'visible_source_regions':4,
            'all_frequency_tables_equal':True,'profiled_runs':9,
            'independent_salary_and_region_checks':True,'mapper_failure_recovered':True,
            'pdf_sha256':hashlib.sha256((ROOT/'output'/'pdf'/'Карташов_Игорь_J3312_MapReduce.pdf').read_bytes()).hexdigest()}
    (ROOT/'evidence'/'final-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


A4_WIDTH=595.2755905511812
A4_HEIGHT=841.8897637795277
if __name__=='__main__':main()
