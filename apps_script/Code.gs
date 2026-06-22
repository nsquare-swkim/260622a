const SHEET_NAME = 'budget';

const HEADERS = [
  'id',
  'created_at',
  'month',
  'member',
  'category',
  'amount',
  'memo'
];

function doGet(e) {
  return jsonResponse({
    ok: true,
    message: 'Budget API is running.'
  });
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents || '{}');
    const action = body.action;

    setupSheet();

    if (action === 'list') {
      return listData();
    }

    if (action === 'append') {
      return appendData(body);
    }

    if (action === 'delete') {
      return deleteData(body);
    }

    return jsonResponse({
      ok: false,
      message: 'Unknown action: ' + action
    });

  } catch (error) {
    return jsonResponse({
      ok: false,
      message: error.toString()
    });
  }
}

function setupSheet() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = spreadsheet.getSheetByName(SHEET_NAME);

  if (!sheet) {
    sheet = spreadsheet.insertSheet(SHEET_NAME);
  }

  const firstRow = sheet.getRange(1, 1, 1, HEADERS.length).getValues()[0];
  const hasHeader = firstRow.join('') !== '';

  if (!hasHeader) {
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
    sheet.setFrozenRows(1);
  }
}

function listData() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  const values = sheet.getDataRange().getValues();

  if (values.length <= 1) {
    return jsonResponse({
      ok: true,
      data: []
    });
  }

  const headers = values[0];
  const rows = values.slice(1);

  const data = rows
    .filter(row => row.some(cell => cell !== ''))
    .map(row => {
      const item = {};
      headers.forEach((header, index) => {
        item[header] = row[index];
      });
      return item;
    });

  return jsonResponse({
    ok: true,
    data: data
  });
}

function appendData(body) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);

  const now = new Date();
  const id = String(now.getTime());

  const row = [
    id,
    Utilities.formatDate(now, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss'),
    body.month || '',
    body.member || '',
    body.category || '',
    Number(body.amount || 0),
    body.memo || ''
  ];

  sheet.appendRow(row);

  return jsonResponse({
    ok: true,
    message: 'saved',
    id: id
  });
}

function deleteData(body) {
  const targetId = String(body.id || '');
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  const values = sheet.getDataRange().getValues();

  for (let i = 1; i < values.length; i++) {
    const rowId = String(values[i][0]);
    if (rowId === targetId) {
      sheet.deleteRow(i + 1);
      return jsonResponse({
        ok: true,
        message: 'deleted',
        id: targetId
      });
    }
  }

  return jsonResponse({
    ok: false,
    message: '삭제할 데이터를 찾지 못했습니다.'
  });
}

function jsonResponse(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}
