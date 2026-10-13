from __future__ import annotations
import copy, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
SOP_PATH = DATA_DIR / 'sops.json'
HISTORY_PATH = DATA_DIR / 'sop_history.json'

SOP_NAMES = {'digistore24':'SOP — Digistore24','adobe_express':'SOP — Adobe Express','pinterest':'SOP — Pinterest'}
DEFAULT_SOPS = {
'digistore24': {'name':SOP_NAMES['digistore24'],'purpose':'Find and review valid Digistore24 products before they enter the DigiFlow pipeline.','steps':['Open the Digistore24 marketplace in the persistent browser workspace.','Navigate to the required marketplace category.','Review candidate products and open the product detail page.','Confirm the product has a usable URL, amount, and other essential details.','Obtain the affiliate/promotion link when required by the workflow.','Reject incomplete, duplicate, or unusable products.','Save only approved unique products to the Product Vault.'],'rules':['Never save a product without a usable URL.','Never save a product without an amount.','Never reuse a previously selected product.','Keep category assignment accurate.','Do not fabricate missing product information.'],'checks':['Product name present','URL present','Amount present','Essential details present','Not already in the permanent product registry'],'do_not_do':['Do not bypass login or CAPTCHA.','Do not store Digistore24 passwords in DigiFlow.','Do not publish or promote a product before review approval.']},
'adobe_express': {'name':SOP_NAMES['adobe_express'],'purpose':'Create a Pinterest-ready visual using the persistent Adobe Express Premium workspace.','steps':['Open Adobe Express in the persistent browser workspace.','Choose a suitable Pinterest 2:3 design/template.','Customize the design with approved product/content information.','Check layout, readability, branding, and image quality.','Export the finished image.','Save and associate the exported asset with the correct product/task.'],'rules':['Use approved product/content information only.','Keep the final design suitable for Pinterest.','Do not invent product claims or testimonials.','Preserve the association between product, content, and asset.'],'checks':['Correct product','Correct Pinterest aspect ratio','Readable text','No unsupported claims','Export completed'],'do_not_do':['Do not store Adobe passwords in DigiFlow.','Do not overwrite approved assets without creating a new version.','Do not publish to Pinterest from the Adobe step.']},
'pinterest': {'name':SOP_NAMES['pinterest'],'purpose':'Prepare a Pinterest Pin from an approved product, copy, and image, stopping before final publication.','steps':['Open Pinterest in the persistent browser workspace.','Start Create Pin.','Attach the approved image.','Enter the approved title and description.','Enter the destination/product URL.','Add relevant keywords where appropriate.','Validate all required fields.','Stop before Publish so the user can perform the final publication manually.'],'rules':['Use only approved product URLs.','Use approved generated copy.','Keep descriptions product-specific and non-misleading.','Final Publish remains a manual user action.'],'checks':['Image attached','Title present','Description present','Destination URL present','Required fields valid','Publish not automatically clicked'],'do_not_do':['Do not store Pinterest passwords in DigiFlow.','Do not click final Publish automatically.','Do not use fabricated statistics, testimonials, or guarantees.']}}

def _now(): return datetime.now(timezone.utc).isoformat()
def _read(path, fallback):
    try:
        with path.open('r',encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError,json.JSONDecodeError,OSError): return copy.deepcopy(fallback)
def _write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8') as f: json.dump(data,f,indent=2,ensure_ascii=False)
    tmp.replace(path)
def _ensure():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    if not SOP_PATH.exists(): _write(SOP_PATH,copy.deepcopy(DEFAULT_SOPS))
    if not HISTORY_PATH.exists(): _write(HISTORY_PATH,[])
    cur=_read(SOP_PATH,{})
    changed=False
    for k,v in DEFAULT_SOPS.items():
        if k not in cur: cur[k]=copy.deepcopy(v); changed=True
    if changed: _write(SOP_PATH,cur)

def _next(s):
    try: return int(s.get('version',1))+1
    except (TypeError,ValueError): return 2

class SOPStore:
    def __init__(self): _ensure()
    def all(self): return _read(SOP_PATH,copy.deepcopy(DEFAULT_SOPS))
    def get(self,key):
        data=self.all()
        if key not in data: raise KeyError(key)
        return data[key]
    def _history(self,key,snapshot,action,actor):
        h=_read(HISTORY_PATH,[])
        entry={'history_id':f'{key}-{len(h)+1}','sop_key':key,'action':action,'actor':actor,'saved_at':_now(),'version':snapshot.get('version',1),'snapshot':copy.deepcopy(snapshot)}
        h.append(entry); _write(HISTORY_PATH,h); return entry
    def save(self,key,data,actor='user'):
        cur=self.get(key); self._history(key,cur,'before_save',actor)
        new=copy.deepcopy(data); new['name']=cur.get('name',SOP_NAMES.get(key,key)); new['version']=_next(cur); new['updated_at']=_now(); new['updated_by']=actor
        all_sops=self.all(); all_sops[key]=new; _write(SOP_PATH,all_sops); return new
    def reset(self,key,actor='user'):
        cur=self.get(key); self._history(key,cur,'before_reset',actor)
        new=copy.deepcopy(DEFAULT_SOPS[key]); new['version']=_next(cur); new['updated_at']=_now(); new['updated_by']=actor; new['reset_from_version']=cur.get('version',1)
        all_sops=self.all(); all_sops[key]=new; _write(SOP_PATH,all_sops); return new
    def history(self,key=None):
        h=_read(HISTORY_PATH,[])
        return list(reversed(h if key is None else [x for x in h if x.get('sop_key')==key]))
    def restore(self,key,history_id,actor='user'):
        cur=self.get(key); h=_read(HISTORY_PATH,[])
        target=next((x for x in h if x.get('history_id')==history_id and x.get('sop_key')==key),None)
        if not target: raise KeyError(history_id)
        self._history(key,cur,'before_restore',actor)
        new=copy.deepcopy(target['snapshot']); new['name']=cur.get('name',SOP_NAMES.get(key,key)); new['version']=_next(cur); new['updated_at']=_now(); new['updated_by']=actor; new['restored_from']=history_id
        all_sops=self.all(); all_sops[key]=new; _write(SOP_PATH,all_sops); return new

sop_store=SOPStore()
