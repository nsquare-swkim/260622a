const BUDGET_SHEET_NAME = 'budget';
const CONFIG_SHEET_NAME = 'config';
const BUDGET_HEADERS = ['id','created_at','month','member','category','amount','memo'];
const CONFIG_HEADERS = ['type','value','created_at'];
const DEFAULT_MEMBERS = ['부장님','팀원1','팀원2','팀원3','팀원4'];
const DEFAULT_CATEGORIES = ['수선유지비','비품','개량공사','대회 활동비'];

function doGet(e){ setupSheets(); return jsonResponse({ok:true,message:'Budget API is running.'}); }
function doPost(e){
  try{
    const body=JSON.parse(e.postData.contents||'{}');
    const action=body.action;
    setupSheets();
    if(action==='list') return listBudgetData();
    if(action==='append') return appendBudgetData(body);
    if(action==='delete') return deleteBudgetData(body);
    if(action==='config') return listConfig();
    if(action==='addConfig') return addConfig(body);
    if(action==='deleteConfig') return deleteConfig(body);
    return jsonResponse({ok:false,message:'Unknown action: '+action});
  }catch(error){ return jsonResponse({ok:false,message:error.toString()}); }
}
function setupSheets(){ setupBudgetSheet(); setupConfigSheet(); }
function setupBudgetSheet(){
  const ss=SpreadsheetApp.getActiveSpreadsheet(); let sheet=ss.getSheetByName(BUDGET_SHEET_NAME);
  if(!sheet) sheet=ss.insertSheet(BUDGET_SHEET_NAME);
  const first=sheet.getRange(1,1,1,BUDGET_HEADERS.length).getValues()[0];
  if(first.join('')===''){ sheet.getRange(1,1,1,BUDGET_HEADERS.length).setValues([BUDGET_HEADERS]); sheet.setFrozenRows(1); }
}
function setupConfigSheet(){
  const ss=SpreadsheetApp.getActiveSpreadsheet(); let sheet=ss.getSheetByName(CONFIG_SHEET_NAME);
  if(!sheet) sheet=ss.insertSheet(CONFIG_SHEET_NAME);
  const first=sheet.getRange(1,1,1,CONFIG_HEADERS.length).getValues()[0];
  if(first.join('')===''){ sheet.getRange(1,1,1,CONFIG_HEADERS.length).setValues([CONFIG_HEADERS]); sheet.setFrozenRows(1); }
  const values=sheet.getDataRange().getValues();
  if(values.length<=1){ DEFAULT_MEMBERS.forEach(v=>appendConfigRow(sheet,'member',v)); DEFAULT_CATEGORIES.forEach(v=>appendConfigRow(sheet,'category',v)); }
}
function listBudgetData(){
  const sheet=SpreadsheetApp.getActiveSpreadsheet().getSheetByName(BUDGET_SHEET_NAME);
  const values=sheet.getDataRange().getValues();
  if(values.length<=1) return jsonResponse({ok:true,data:[]});
  const headers=values[0];
  const data=values.slice(1).filter(r=>r.some(c=>c!=='')).map(r=>{ const item={}; headers.forEach((h,i)=>item[h]=r[i]); return item; });
  return jsonResponse({ok:true,data:data});
}
function appendBudgetData(body){
  const sheet=SpreadsheetApp.getActiveSpreadsheet().getSheetByName(BUDGET_SHEET_NAME);
  const now=new Date(); const id=String(now.getTime());
  sheet.appendRow([id, Utilities.formatDate(now, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss'), body.month||'', body.member||'', body.category||'', Number(body.amount||0), body.memo||'']);
  return jsonResponse({ok:true,message:'saved',id:id});
}
function deleteBudgetData(body){
  const targetId=String(body.id||'');
  const sheet=SpreadsheetApp.getActiveSpreadsheet().getSheetByName(BUDGET_SHEET_NAME);
  const values=sheet.getDataRange().getValues();
  for(let i=1;i<values.length;i++){ if(String(values[i][0])===targetId){ sheet.deleteRow(i+1); return jsonResponse({ok:true,message:'deleted',id:targetId}); } }
  return jsonResponse({ok:false,message:'삭제할 데이터를 찾지 못했습니다.'});
}
function listConfig(){
  const sheet=SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG_SHEET_NAME);
  const values=sheet.getDataRange().getValues();
  const result={members:[],categories:[]};
  if(values.length<=1) return jsonResponse({ok:true,data:result});
  values.slice(1).forEach(r=>{
    const type=String(r[0]||'').trim(); const value=String(r[1]||'').trim();
    if(!value) return;
    if(type==='member' && result.members.indexOf(value)===-1) result.members.push(value);
    if(type==='category' && result.categories.indexOf(value)===-1) result.categories.push(value);
  });
  return jsonResponse({ok:true,data:result});
}
function addConfig(body){
  const type=String(body.type||'').trim(); const value=String(body.value||'').trim();
  if(!isValidConfigType(type)) return jsonResponse({ok:false,message:'잘못된 설정 타입입니다.'});
  if(!value) return jsonResponse({ok:false,message:'추가할 값을 입력하세요.'});
  const sheet=SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG_SHEET_NAME);
  const values=sheet.getDataRange().getValues();
  for(let i=1;i<values.length;i++){ if(String(values[i][0]).trim()===type && String(values[i][1]).trim()===value) return jsonResponse({ok:false,message:'이미 등록된 값입니다.'}); }
  appendConfigRow(sheet,type,value);
  return jsonResponse({ok:true,message:'added',type:type,value:value});
}
function deleteConfig(body){
  const type=String(body.type||'').trim(); const value=String(body.value||'').trim();
  if(!isValidConfigType(type)) return jsonResponse({ok:false,message:'잘못된 설정 타입입니다.'});
  if(!value) return jsonResponse({ok:false,message:'삭제할 값을 입력하세요.'});
  const sheet=SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG_SHEET_NAME);
  const values=sheet.getDataRange().getValues();
  for(let i=1;i<values.length;i++){ if(String(values[i][0]).trim()===type && String(values[i][1]).trim()===value){ sheet.deleteRow(i+1); return jsonResponse({ok:true,message:'deleted',type:type,value:value}); } }
  return jsonResponse({ok:false,message:'삭제할 값을 찾지 못했습니다.'});
}
function appendConfigRow(sheet,type,value){
  const now=new Date();
  sheet.appendRow([type,value,Utilities.formatDate(now, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss')]);
}
function isValidConfigType(type){ return type==='member' || type==='category'; }
function jsonResponse(payload){ return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(ContentService.MimeType.JSON); }
