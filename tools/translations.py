#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import re
import sys

from io import BytesIO

from babel.messages import Catalog, Message
from babel.messages.pofile import read_po, write_po
from babel.util import distinct

MAX_LENGTH = 5000
TIMEOUT = 1
SEPARATOR = '\n|'

def dir_type(string):
    if os.path.isdir(string):
        return string

    raise argparse.ArgumentTypeError('путь {0} не является каталогом'.format(string))

def message_key(message):
    """Ключ для сравнения сообщений без учёта регистра"""

    if isinstance(message, Message) and message.pluralizable:
        return message.id[0].casefold(), (message.context or '').casefold()
    return message.id.casefold(), (message.context or '').casefold()

def extract_field_by_spec(entry, spec):
    """Извлекает значение из записи по спецификации поиска"""
    field = spec['field']

    if 'path' not in spec:
        if field not in entry:
            return None

        return entry[field]

    path = spec['path']

    if path not in entry:
        return None

    def check(link, conditions):
        for key, value in conditions:
            if link[key] != value:
                return False

        return True

    conditions = spec['conditions']
    for link in entry[path]:
        if check(link, conditions):
            return link[field]

    return None

def extract(args):
    """Команда извлечения строк перевода"""

    if args.output is None or not os.path.exists(args.output):
        catalog = Catalog(project='Twokinds Suggestions', version='1.0')
    else:
        with open(args.output, 'rb') as f:
            catalog = read_po(f)

            # Очищаем существующие местоположения, поскольку они уже могли устареть
            for message in catalog:
                message.locations = []
                message.auto_comments = []
                # Сбрасываем некорректно установливаемый флаг python-format в конструкторе Message
                message.flags.discard('python-format')

    for f in args.files:
        extract_from_file(catalog, f)

    if args.output is None:
        f = BytesIO()
        write_po(f, catalog, sort_output=True, width=None)

        print(f.getvalue().decode('utf8'))
    else:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, 'wb') as f:
            write_po(f, catalog, sort_output=True, width=None)

def extract_from_file(catalog, file):
    """Извлекает строки для перевода из файла и помещает их в каталог"""

    with file:
        file_name = file.name
        file_content = file.read()
        votes = json.loads(file_content)

        # Извлекаем комментарий, если есть
        if 'comment' in votes:
            locations = get_locations('comment', votes['comment'], file_name, file_content)
            add_to_catalog(votes['comment'], catalog, locations=locations, context='comment')

        # Извлекаем предложения
        for v in votes['data']:
            locations = get_locations('suggestion', v['suggestion'], file_name, file_content)
            auto_comments = get_auto_comments(v)
            add_to_catalog(v['suggestion'], catalog, locations=locations, auto_comments=auto_comments)

            for value in additional_translations(v):
                locations = get_locations('name', value, file_name, file_content)
                add_to_catalog(value, catalog, locations=locations, context='publish_name')

def additional_translations(entry):
    """Генератор, возвращающий список дополнительных значений для перевода"""
    specs = (
        { 'field': 'name', 'path': 'links', 'conditions': (('type', 'sketch',),) },
        { 'field': 'name', 'path': 'links', 'conditions': (('type', 'color',),) },
    )

    for spec in specs:
        value = extract_field_by_spec(entry, spec)
        if value:
            yield value

def get_locations(key, message, file_name, file_content):
    """Определяет местоположения сообщения в json-файле"""
    locations = []
    message = re.escape(message.replace('"', '\\"'))
    pattern = f'"{key}"\s*:\s*"(?P<message>{message})"'

    for pos in [m.start('message') for m in re.finditer(pattern, file_content)]:
        line_no = file_content.count('\n', 0, pos) + 1
        locations.append((file_name, line_no))

    return locations

def get_auto_comments(entry):
    """Извлекает из записи предложения дополнительные метаданные в виде пользовательских комментариев"""
    comments = []

    specs = {
        'Дата': { 'field': 'date', 'path': 'links', 'conditions': (('type', 'sketch',),) },
        'Название': { 'field': 'name', 'path': 'links', 'conditions': (('type', 'sketch',),) },
        'Предложил': { 'field': 'suggested_by' },
        'Ссылка (Patreon)': { 'field': 'link', 'path': 'links', 'conditions': (('type', 'sketch',), ('site', 'patreon',),) },
        'Ссылка (DeviantArt)': { 'field': 'link', 'path': 'links', 'conditions': (('type', 'sketch',), ('site', 'deviantart',),) },
        'Ссылка (Twitter)': { 'field': 'link', 'path': 'links', 'conditions': (('type', 'sketch',), ('site', 'twitter',),) },

        'Дата цветной версии': { 'field': 'date', 'path': 'links', 'conditions': (('type', 'color',),) },
        'Название цветной версии': { 'field': 'name', 'path': 'links', 'conditions': (('type', 'color',),) },
        'Место в голосовании за цветную версию': { 'field': 'color_position' },
        'Спонсор': { 'field': 'sponsored_by' },
        'Ссылка на цветную версию (Patreon)': { 'field': 'link', 'path': 'links', 'conditions': (('type', 'color',), ('site', 'patreon',),) },
        'Ссылка на цветную версию (DeviantArt)': { 'field': 'link', 'path': 'links', 'conditions': (('type', 'color',), ('site', 'deviantart',),) },
        'Ссылка на цветную версию (Twitter)': { 'field': 'link', 'path': 'links', 'conditions': (('type', 'color',), ('site', 'twitter',),) },
    }

    for field, spec in specs.items():
        value = extract_field_by_spec(entry, spec)
        if value:
            if isinstance(value, list):
                for v in value:
                    comments.append(f":{field}: {v}")
            else:
                comments.append(f":{field}: {value}")

    return comments

def add_to_catalog(message, catalog, locations=(), auto_comments=(), context=None):
    """Добавляет сообщение в каталог"""

    m = catalog.get(message, context)
    if m:
        m.locations = list(set(m.locations + list(locations)))
        m.auto_comments = list(distinct(m.auto_comments + list(auto_comments)))
    else:
        catalog.add(message, locations=locations, auto_comments=auto_comments, context=context)

        # Сбрасываем некорректно установливаемый флаг python-format в конструкторе Message
        m = catalog.get(message, context)
        m.flags.discard('python-format')

def apply(args):
    """Команда применения строк перевода"""

    with args.catalog:
        catalog = read_po(args.catalog)

    os.makedirs(args.dir, exist_ok=True)

    all_additional = {
      'language': catalog.locale.language,
      'publish_name': {}
    }

    for f in args.files:
        data, additional = get_translations(catalog, f)

        all_additional['publish_name'].update(additional['publish_name'])

        file_name = os.path.join(args.dir, os.path.basename(f.name))
        with open(file_name, 'w', encoding='utf8', newline='\n') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    all_additional['publish_name'] = dict(sorted(all_additional['publish_name'].items()))

    additional_file_name = os.path.join(args.dir, 'additional.json')
    with open(additional_file_name, 'w', encoding='utf8', newline='\n') as f:
        json.dump(all_additional, f, indent=2, ensure_ascii=False)

def get_translations(catalog, file):
    """Получение списка переведённых строк предложения/комментариев и меток"""

    data = {
      'language': None,
      'comment': None,
      'suggestions': []
    }

    additional = {
      'language': None,
      'publish_name': {}
    }

    with file:
        votes = json.load(file)

        data['language'] = catalog.locale.language
        additional['language'] = catalog.locale.language

        # Извлекаем перевод комментария, если есть
        if 'comment' in votes:
            data['comment'] = get_from_catalog(catalog, votes['comment'], 'comment')

        # Извлекаем переводы предложений и опубликованных работ
        for v in votes['data']:
            translation = get_from_catalog(catalog, v['suggestion'])
            data['suggestions'].append(translation)

            for value in additional_translations(v):
                translation = get_from_catalog(catalog, value, context='publish_name')
                if translation:
                    additional['publish_name'][value] = translation

    return data, additional

def get_from_catalog(catalog, id, context=None):
    """Извлекает переведённое сообщение из каталога"""

    message = catalog.get(id, context)
    if message and message.string and not message.fuzzy:
        return message.string

    return None

def translate(args):
    """Команда автоматического перевода po-файла"""

    try:
        import translators
    except ImportError:
        print('''Не установлен модуль translate-api.

Для перевода установите модуль::

  pip install translate-api
''')
        return

    from time import sleep

    service = getattr(translators, args.service)

    with args.catalog:
        catalog = read_po(args.catalog)

    data = [m.id for m in catalog if m.id != '' and (not m.string or m.fuzzy)]

    length = 0
    chunks = []
    chunks_count = 0
    i = 1
    s = len(SEPARATOR)

    for m in data:
        l = len(m)
        if length + l + chunks_count*s < MAX_LENGTH:
            length += l
            chunks_count += 1
            chunks.append(m)
        else:
            process_chunks(chunks, chunks_count, i, catalog, service)

            length = 0
            chunks = []
            chunks_count = 0
            i += 1

            # Чтобы не смущать сервис чрезмерным количеством запросов
            sleep(TIMEOUT)

    if chunks_count > 0:
        process_chunks(chunks, chunks_count, i, catalog, service)

    with open(args.catalog.name, 'wb') as f:
        write_po(f, catalog, sort_output=True, width=None)


def process_chunks(chunks, chunks_count, i, catalog, translate_service):
    result = translate_service(
        SEPARATOR.join(chunks),
        from_language='en',
        to_language=catalog.locale.language,
        sleep_seconds=0.06
    )
    print(f'Обработка части {i} завершена')

    result = result.split(SEPARATOR)
    result_count = len(result)
    if chunks_count != result_count:
        print(
            f'Количество строк оригинала {chunks_count} '
            f'не соответствует количеству строк {result_count} '
            'полученного перевода'
        )

    for message, string in zip(chunks, result):
       m = catalog[message]
       m.string = string.strip()
       m.flags.add('fuzzy')


def format_json(args):
    """Команда форматирования json-файлов"""

    for f in args.files:
        with f:
            content = json.load(f)

        with open(f.name, 'w', encoding='utf8', newline='\n') as f:
            json.dump(content, f, indent=2, ensure_ascii=False)

def get_parser():
    parser = argparse.ArgumentParser(description='Работа с переводами в указанных каталогах.')
    parser.set_defaults(command=lambda *args: parser.print_help())

    subparsers = parser.add_subparsers(title='подкоманды', description='доступные подкоманды')

    # Извлечение переводов
    parser_extract = subparsers.add_parser('extract', help='Извлечение строк для перевода в po-файл gettext.')
    parser_extract.add_argument('files'
        , help='файлы, из которых нужно извлечь строки для перевода'
        , metavar='FILE'
        , type=argparse.FileType('r', encoding='utf-8')
        , nargs='+'
    )
    parser_extract.add_argument('--output', '-o'
        , help='po-файл gettext, в который следует собрать переводимые строки'
        , metavar='LANGFILE'
    )
    parser_extract.set_defaults(command=extract)

    # Применение переводов
    parser_apply = subparsers.add_parser('apply', help='Применение переводов из po-файла gettext к данным в json-файлах.')
    parser_apply.add_argument('catalog'
        , help='po-файл gettext с готовыми переводами'
        , metavar='LANGFILE'
        , type=argparse.FileType('r', encoding='utf-8')
    )
    parser_apply.add_argument('dir'
        , help='каталог, в который нужно сложить результирующие json-файлы с переводом'
        , metavar='DIR'
        , type=dir_type
    )
    parser_apply.add_argument('files'
        , help='файлы, из которых нужно извлечь строки для перевода'
        , metavar='FILE'
        , type=argparse.FileType('r', encoding='utf-8')
        , nargs='+'
    )
    parser_apply.set_defaults(command=apply)

    # Автоматический перевод (если доступен)
    parser_translate = subparsers.add_parser('translate', help='Автоматический перевод из po-файла gettext к данным в json-файлах.')
    parser_translate.add_argument('catalog'
        , help='po-файл gettext со строками для перевода'
        , metavar='LANGFILE'
        , type=argparse.FileType('r', encoding='utf-8')
    )
    parser_translate.add_argument('--service'
        , help='сервис автоматического перевода'
        , metavar='SERVICE'
        , default='google'
        , choices=('alibaba', 'baidu', 'bing', 'deepl', 'google', 'sogou', 'tencent', 'yandex', 'youdao')
    )
    parser_translate.set_defaults(command=translate)

    # Форматирование json-файлов
    parser_format = subparsers.add_parser('format', help='Форматирование json-файлов.')
    parser_format.add_argument('files'
        , help='файлы, которые нужно отформатировать'
        , metavar='FILE'
        , type=argparse.FileType('r', encoding='utf-8')
        , nargs='+'
    )
    parser_format.set_defaults(command=format_json)

    return parser

def main():
    args = get_parser().parse_args()
    args.command(args)

if __name__ == '__main__':
    main()
