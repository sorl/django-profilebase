import re


uncamel_patterns = (
    re.compile('(.)([A-Z][a-z]+)'),
    re.compile('([a-z0-9])([A-Z])'),
    )


def uncamel(s):
    """
    Make camelcase lowercase and use underscores.

        >>> uncamel('CamelCase')
        'camel_case'
        >>> uncamel('CamelCamelCase')
        'camel_camel_case'
        >>> uncamel('Camel2Camel2Case')
        'camel2_camel2_case'
        >>> uncamel('getHTTPResponseCode')
        'get_http_response_code'
        >>> uncamel('get2HTTPResponseCode')
        'get2_http_response_code'
        >>> uncamel('HTTPResponseCode')
        'http_response_code'
        >>> uncamel('HTTPResponseCodeXYZ')
        'http_response_code_xyz'
    """
    for pat in uncamel_patterns:
        s = pat.sub(r'\1_\2', s)
    return s.lower()

