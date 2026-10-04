"""Bounded PDF inspection subprocess; no Django or storage access."""
import json
import logging
import resource
import sys


def inspect_pdf(path):
    # Linux production enforces the address-space bound. macOS does not
    # support lowering these limits reliably; local checks retain the same
    # byte, page, object, CPU and parent-enforced wall-clock limits.
    if sys.platform == 'linux':
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    logging.disable(logging.CRITICAL)
    from pypdf import PdfReader
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
    reader = PdfReader(path, strict=True)
    if reader.is_encrypted:
        return {'error': 'PDF защищён паролем. Экспортируйте документ без защиты.'}
    count = len(reader.pages)
    if count < 1 or count > 200:
        return {'error': 'PDF должен содержать от 1 до 200 страниц.'}
    prohibited_keys = {'/JS', '/JavaScript', '/AA', '/OpenAction', '/EmbeddedFiles', '/EF', '/AF',
                       '/AcroForm', '/RichMedia', '/XFA'}
    prohibited_actions = {'/JavaScript', '/Launch', '/SubmitForm', '/ImportData', '/GoToR'}
    seen_refs, seen_objects = set(), set()
    stack = [reader.trailer]
    visited = 0
    while stack:
        visited += 1
        if visited > 100_000:
            return {'error': 'Структура PDF слишком сложная. Экспортируйте обычный PDF для печати.'}
        item = stack.pop()
        if isinstance(item, IndirectObject):
            key = (item.idnum, item.generation)
            if key in seen_refs:
                continue
            seen_refs.add(key)
            stack.append(item.get_object())
        elif isinstance(item, (DictionaryObject, ArrayObject)):
            identity = id(item)
            if identity in seen_objects:
                continue
            seen_objects.add(identity)
            if isinstance(item, DictionaryObject):
                if prohibited_keys.intersection(item.keys()) or item.get('/S') in prohibited_actions:
                    return {'error': 'PDF содержит вложения, сценарии или интерактивные формы. Экспортируйте обычный PDF для печати.'}
                stack.extend(item.values())
            else:
                stack.extend(item)
    return {'pages': count}


if __name__ == '__main__':
    try:
        result = inspect_pdf(sys.argv[1])
    except Exception:
        result = {'error': 'PDF повреждён или имеет неподдерживаемую структуру. Экспортируйте документ заново.'}
    print(json.dumps(result))
