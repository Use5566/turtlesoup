"""Teacher-facing text and separate recovery notes for the same cells."""
import json

PREFIX = 'TURTLESOUP_RECORDS_V1\n'
STATUS = {'processing': '處理中', 'rephrase': '請改成可用肯定或否定回答的問題。',
          'uncertain': '題目資訊不足以判斷。', 'service_error': '主持人暫時無法回應。',
          'invalid_output': '回答格式不符。', 'not_configured': '主持人尚未啟用。',
          'interrupted': '提問中斷，結果未確認。'}


def decode(raw, note, student):
    if note:
        if not note.startswith(PREFIX):
            raise ValueError('既有備註非系統格式，保留原資料')
        envelope = json.loads(note[len(PREFIX):])
        if envelope['student'] != student:
            raise ValueError('備註身分與資料列不符')
        records = envelope['records']
    else:
        records = json.loads(raw) if raw else {}
    if not isinstance(records, dict) or any(not isinstance(v, dict) for v in records.values()):
        raise ValueError('既有紀錄格式不符，保留原內容')
    return records


def readable(records, summary=False):
    blocks = []
    for record in records.values():
        if summary:
            state = '已結束' if record.get('場次狀態') == 'finished' else '進行中'
            blocks.append(f"開始：{record.get('開始時間', '')}\n"
                          f"最後互動：{record.get('最後互動時間', '')}\n"
                          f"提問：{record.get('提問總數', 0)} 次｜{state}")
        else:
            answer = record.get('AI回答') or STATUS.get(record.get('處理狀態'), '尚無回答')
            blocks.append(f"{record.get('紀錄時間', '')}\n學生：{record.get('學生問題', '')}\n主持人：{answer}")
    return '\n\n'.join(blocks)


def cell(records, student, summary=False):
    value = readable(records, summary)
    note = PREFIX + json.dumps({'student': student, 'records': records}, ensure_ascii=False, separators=(',', ':'))
    if any(len(s.encode('utf-16-le')) // 2 > 49000 for s in (value, note)):
        raise ValueError('紀錄接近容量上限，請先封存紀錄')
    return {'userEnteredValue': {'stringValue': value}, 'note': note,
            'userEnteredFormat': {'wrapStrategy': 'CLIP', 'verticalAlignment': 'TOP'}}
