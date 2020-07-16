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

def dir_type(string):
    if os.path.isdir(string):
        return string

    raise ArgumentTypeError('путь {0} не является каталогом'.format(string))

def message_key(message):
    """Ключ для сравнения сообщений без учёта регистра"""

    if isinstance(message, Message) and message.pluralizable:
        return message.id[0].casefold(), (message.context or '').casefold()
    return message.id.casefold(), (message.context or '').casefold()

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
            add_to_catalog(v['suggestion'], catalog, locations=locations)

def get_locations(key, message, file_name, file_content):
    """Определяет местоположения сообщения в json-файле"""
    locations = []
    message = re.escape(message.replace('"', '\\"'))
    pattern = f'"{key}"\s*:\s*"(?P<message>{message})"'

    for pos in [m.start('message') for m in re.finditer(pattern, file_content)]:
        line_no = file_content.count('\n', 0, pos) + 1
        locations.append((file_name, line_no))

    return locations

def add_to_catalog(message, catalog, locations=None, context=None):
    """Добавляет сообщение в каталог"""

    if message not in catalog:
       catalog.add(message, locations=locations, context=context)
    else:
       s = set(catalog[message].locations)
       s |= frozenset(locations)
       catalog[message].locations = list(s)

def apply(args):
    """Команда применения строк перевода"""

    with args.catalog:
        catalog = read_po(args.catalog)

    os.makedirs(args.dir, exist_ok=True)
    for f in args.files:
        data = get_translations(catalog, f)
        file_name = os.path.join(args.dir, os.path.basename(f.name))
        with open(file_name, 'w', encoding='utf8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

def get_translations(catalog, file):
    """Получение списка переведённых строк предложения/комментариев и меток"""

    data = {
      'language': None,
      'comment': None,
      'suggestions': []
    }

    with file:
        votes = json.load(file)

        data['language'] = catalog.locale.language

        # Извлекаем перевод комментария, если есть
        if 'comment' in votes:
            data['comment'] = get_from_catalog(catalog, votes['comment'], 'comment')

        # Извлекаем переводы предложений
        for v in votes['data']:
            translation = get_from_catalog(catalog, v['suggestion'])
            data['suggestions'].append(translation)

    return data

def get_from_catalog(catalog, id, context=None):
    """Извлекает переведённое сообщение из каталога"""

    message = catalog.get(id, context)
    if message and message.string and not message.fuzzy:
        return message.string

    return None

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

    return parser

def main():
    args = get_parser().parse_args()
    args.command(args)

if __name__ == '__main__':
    main()
