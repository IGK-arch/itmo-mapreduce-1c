"""Evidence, arithmetic, screenshot provenance and final PDF layout checks."""
import hashlib
import json
import re
import statistics

import bootstrap
from bootstrap import ROOT
import pymupdf


def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))


def main():
    verification=read('evidence/verification.json')
    assert verification['all_equal'] and verification['mapper_failure_recovered']
    assert verification['selected_vacancies']==read('evidence/source-audit.json')['counts']['selected_vacancies']==18164
    assert verification['compared_runs']==10
    runs=read('evidence/benchmark-runs.json')
    assert len(runs)==9
    for method in ('baseline','optimized','duckdb'):
        subset=[r for r in runs if r['method']==method]
        assert len(subset)==3 and {r['trial'] for r in subset}=={1,2,3}
        assert all(r['exit_code']==0 and r['peak_process_tree_rss_bytes']>0 for r in subset)
        summary=read('evidence/benchmark-summary.json')[method]
        assert statistics.median(r['wall_seconds'] for r in subset)==summary['median_wall_seconds']
        assert statistics.median(r['peak_process_tree_rss_bytes']/1048576 for r in subset)==summary['median_peak_rss_mib']
    analysis_check=read('evidence/analysis-validation.json')
    assert analysis_check['all_checks_passed']
    assert analysis_check['selected_vacancies']==verification['selected_vacancies']
    terminal_check=read('evidence/terminal-verification.json')
    assert terminal_check['all_equal'] and terminal_check['selected_vacancies']==18164
    assert len(terminal_check['results_in_s3'])==6
    assert all(r['readback_matches'] for r in terminal_check['results_in_s3'])
    assert [r['different_keys'] for r in terminal_check['comparisons']]==[0,0,0]
    sessions=read('evidence/terminal-sessions.json')
    assert [r['action'] for r in sessions]==['compute','verify']
    assert all(r['exit_code']==0 for r in sessions)
    for path,digest in read('evidence/calculation-source-sha256.json').items():
        assert hashlib.sha256((ROOT/path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==digest,path
    pdf=pymupdf.open(ROOT/'output'/'pdf'/'Карташов_Игорь_J3312_MapReduce.pdf')
    assert len(pdf)==13
    for i,page in enumerate(pdf):
        assert len(page.get_text())>150
        for block in page.get_text('blocks'):
            assert block[0]>=18 and block[2]<=page.rect.width-18,(i+1,block[:4])
            assert block[1]>=15 and block[3]<=page.rect.height-15,(i+1,block[:4])
    text='\n'.join(page.get_text() for page in pdf)
    repository=read('evidence/repository.json')['url']
    assert any(link.get('uri')==repository for page in pdf for link in page.get_links())
    for token in ['ОТЧЁТ ПО ЛАБОРАТОРНОЙ РАБОТЕ 3','18 164','229 388','632 469','174 582','7 594','270 000','259 500','137 500','200 000','175 000','150 000']:
        assert token in text,token
    for old_token in ['18 165','632 504','174 615','205 239']:
        assert old_token not in text,old_token
    for number in range(1,10):
        assert text.count(f'Рисунок {number}.')==1
    for run in runs:
        assert f"{run['wall_seconds']:.2f}".replace('.',',') in text
        assert f"{run['peak_process_tree_rss_bytes']/1048576:.1f}".replace('.',',') in text
    assert 'приложены в ZIP' not in text and 'полные журналы приложены' not in text
    images={hashlib.sha256(pdf.extract_image(image[0])['image']).hexdigest()
            for page in pdf for image in page.get_images(full=True)}
    expected={hashlib.sha256((ROOT/'evidence'/'screenshots'/name).read_bytes()).hexdigest()
              for name in ['raw-objects.jpg','mapreduce-results.jpg','csv-properties.jpg',
                           'sql-filter.jpg','skills-preview.jpg','benchmark-runs.jpg','result-checks.jpg',
                           'terminal-compute.jpg','terminal-verify.jpg']}
    assert images==expected and len(images)==9
    manifest=read('evidence/screenshots-manifest.json')
    assert len(manifest)==9 and {r['sha256'] for r in manifest}==expected
    views=read('evidence/pdf-image-views.json')
    assert len(views)==15
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
    result={'passed':True,'pages':len(pdf),'unique_screenshots':9,'visible_source_regions':15,
            'all_frequency_tables_equal':True,'profiled_runs':9,
            'independent_salary_and_region_checks':True,'mapper_failure_recovered':True,
            'repeated_console_runs_and_s3_readback':True,
            'pdf_sha256':hashlib.sha256((ROOT/'output'/'pdf'/'Карташов_Игорь_J3312_MapReduce.pdf').read_bytes()).hexdigest()}
    (ROOT/'evidence'/'final-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


A4_WIDTH=595.2755905511812
A4_HEIGHT=841.8897637795277
if __name__=='__main__':main()
