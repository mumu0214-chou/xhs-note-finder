#!/usr/bin/env python3
"""Maintain a shared source/template/usage ledger and a readable Markdown view."""
import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile

GROUPS = ('sources', 'templates', 'products', 'uses')

def empty():
    return {'schema_version': 1, **{key: {} for key in GROUPS}, 'events': []}

def merge_dict(old, new):
    result = copy.deepcopy(old)
    for key, value in new.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result

def validate(data):
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported schema_version')
    for group in GROUPS:
        if not isinstance(data.get(group), dict):
            raise ValueError(f'{group} must be an object')
        for key, record in data[group].items():
            if not isinstance(record, dict) or record.get('id') != key:
                raise ValueError(f'{group}/{key}: record id must match key')
    for use in data['uses'].values():
        for field, group in [('source_id', 'sources'), ('template_id', 'templates'), ('product_id', 'products')]:
            if use.get(field) not in data[group]:
                raise ValueError(f"{use['id']}: unknown {field}")
        rewrite = use.get('rewrite', {})
        variants = use.get('variants', {})
        if rewrite.get('status', 'pending') not in ('pending', 'done'):
            raise ValueError('Invalid rewrite status')
        if variants.get('status', 'pending') not in ('pending', 'done'):
            raise ValueError('Invalid variants status')
        count = variants.get('count', 0)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError('Variant count must be a nonnegative integer')
        if count and variants.get('status') != 'done':
            raise ValueError('Nonzero variants require completed status')
        if variants.get('status') == 'done' and rewrite.get('status') != 'done':
            raise ValueError('Completed variants require a completed mother draft')
        if use.get('feedback', {}).get('status', 'unknown') not in ('unknown', 'approved', 'rejected', 'revise'):
            raise ValueError('Invalid feedback status')
        if use.get('publication', {}).get('status', 'unknown') not in ('unknown', 'published'):
            raise ValueError('Invalid publication status')
    events = data.get('events', [])
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        raise ValueError('Events must be an array of objects')
    ids = [event.get('id') for event in events]
    if not all(isinstance(event_id, str) and event_id for event_id in ids) or len(set(ids)) != len(ids):
        raise ValueError('Events require unique IDs')

def cell(value):
    return str(value if value is not None else '未知').replace('|', '／').replace('\n', ' ')

def counts(data):
    uses = list(data['uses'].values())
    return {'原笔记': len(data['sources']), '模板类型': len(data['templates']),
            '已完成母稿': sum(u.get('rewrite', {}).get('status') == 'done' for u in uses),
            '已完成裂变篇数': sum(u.get('variants', {}).get('count', 0) for u in uses),
            '获认可的使用记录': sum(u.get('feedback', {}).get('status') == 'approved' for u in uses)}

def render(data):
    out = ['# 小红书笔记共用台账', '',
           '按产品和项目共用。认可表示用户采用意愿；发布及成交效果有独立证据才记录。', '',
           ' · '.join(f'{key}：{value}' for key, value in counts(data).items()), '',
           '历史稿位置按实际记录指向聊天；尚未联调写作技能自动回写。', '',
           '## 原笔记与使用情况', '',
           '| 编号 | 原笔记 | 产品 | 模板 | 母稿 | 裂变篇数 | 反馈 | 发布 |',
           '| --- | --- | --- | --- | --- | ---: | --- | --- |']
    for use in data['uses'].values():
        source = data['sources'][use['source_id']]
        template = data['templates'][use['template_id']]
        product = data['products'][use['product_id']]
        link = f"[{cell(source.get('title'))}]({source.get('url', '')})"
        feedback = {'approved': '已认可', 'unknown': '未知', 'rejected': '未采用', 'revise': '待修改'}[use.get('feedback', {}).get('status', 'unknown')]
        out.append('| ' + ' | '.join([cell(use['id']), link, cell(product.get('name')), cell(template.get('name')),
                    '已改写' if use.get('rewrite', {}).get('status') == 'done' else '待改写',
                    str(use.get('variants', {}).get('count', 0)), feedback,
                    '已发布' if use.get('publication', {}).get('status') == 'published' else '未知']) + ' |')
    used_ids = {u['source_id'] for u in data['uses'].values()}
    unused = [s for s in data['sources'].values() if s['id'] not in used_ids]
    if unused:
        out += ['', '## 尚无使用记录的候选', '']
        for source in unused:
            out.append(f"- [{cell(source.get('title'))}]({source.get('url', '')}) — {cell(source.get('reading_scope'))}")
    out += ['', '## 模板观察', '', '| 模板 | 完成母稿数 | 认可记录数 | 最近采用 | 复查结论 |', '| --- | ---: | ---: | --- | --- |']
    for template in data['templates'].values():
        uses = [u for u in data['uses'].values() if u['template_id'] == template['id'] and u.get('rewrite', {}).get('status') == 'done']
        approved = [u for u in uses if u.get('feedback', {}).get('status') == 'approved']
        dates = [u.get('rewrite', {}).get('completed_at') for u in uses if u.get('rewrite', {}).get('completed_at')]
        out.append('| ' + ' | '.join(map(cell, [template.get('name'), len(uses), len(approved), max(dates) if dates else '未知', template.get('review_status', '新候选')])) + ' |')
    out += ['', '## 稿件位置与反馈依据', '']
    for use in data['uses'].values():
        out += [f"- **{cell(use['id'])}**：{cell(use.get('rewrite', {}).get('title'))}",
                f"  - 位置：{cell(use.get('rewrite', {}).get('output_location'))}",
                f"  - 反馈：{cell(use.get('feedback', {}).get('quote'))}"]
        if use.get('variants', {}).get('count', 0):
            out.append(f"  - 裂变稿位置：{cell(use['variants'].get('output_location'))}")
    out += ['', '详细阅读范围、日期、结构和事件记录见同目录 ledger.json。', '']
    return '\n'.join(out)

def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['show', 'merge', 'render'])
    parser.add_argument('--root', type=Path, default=Path.home() / 'Documents/Codex/小红书笔记台账')
    parser.add_argument('--input', type=Path)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    path = root / 'ledger.json'
    if args.command == 'show':
        data = json.loads(path.read_text()) if path.exists() else empty()
        validate(data)
        print(json.dumps({'root': str(root), 'counts': counts(data), 'ledger': data}, ensure_ascii=False, indent=2))
        return
    if args.command == 'merge' and args.input is None:
        parser.error('merge requires --input')
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.ledger.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text()) if path.exists() else empty()
        validate(data)
        if args.command == 'merge':
            delta = json.loads(args.input.read_text())
            if not isinstance(delta, dict):
                raise ValueError('Update must be an object')
            if set(delta) - set(GROUPS) - {'events', 'schema_version'}:
                raise ValueError('Unknown top-level fields')
            validate({**empty(), 'events': delta.get('events', [])})
            events = {e['id']: e for e in data['events']}
            for event in delta.get('events', []):
                if event['id'] in events and events[event['id']] != event:
                    raise ValueError('Conflicting event ID; use a new event for corrections')
                events[event['id']] = event
            data = merge_dict(data, {k: v for k, v in delta.items() if k != 'events'})
            data['events'] = list(events.values())
            validate(data)
            if path.exists():
                shutil.copy2(path, root / 'ledger.json.bak')
            atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        atomic_write(root / '笔记台账.md', render(data))
    print(json.dumps({'root': str(root), 'counts': counts(data), 'view': str(root / '笔记台账.md')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
