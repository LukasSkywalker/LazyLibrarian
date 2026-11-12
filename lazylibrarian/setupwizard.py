#  This file is part of Lazylibrarian.
#
# Purpose:
#    The setup wizard: typical settings for the user's country, guessed from the browser languages.
#    The wizard shows each proposal next to the current value and saves only the rows the user ticks.
#    Book language codes, month names and magazine words come from booklanguages.py and
#    monthlanguages.py, so a language added there is available here too.
# SPDX-License-Identifier: GPL-3.0-or-later

import contextlib
import copy
import locale
import logging
import os

import lazylibrarian
from lazylibrarian import i18n
from lazylibrarian.booklanguages import BOOK_LANGUAGES
from lazylibrarian.i18n import N_
from lazylibrarian.monthlanguages import LANGUAGE_WORDS, MONTH_LANGUAGES

GENERIC = '_generic'
MONTH_LANGUAGE = 'MONTH_LANGUAGE'  # pseudo key, adds a built-in language to the month name table

# Per language: date order, series number wording, other languages readers of it usually want,
# and the switch of a metadata source for books in it.
LANGUAGES = {
    'sk': {'date': '$d.$m.$Y', 'sernum': 'Kniha č.$SerNum -$$', 'also': ['cs'], 'source': 'DBK_API'},
    'cs': {'date': '$d.$m.$Y', 'sernum': 'Kniha č.$SerNum -$$', 'also': ['sk'], 'source': 'DBK_API'},
    'de': {'date': '$d.$m.$Y', 'sernum': 'Band $SerNum -$$', 'source': 'DNB_API'},
    'pl': {'date': '$d.$m.$Y', 'sernum': 'Tom $SerNum -$$', 'source': 'BN_API'},
    'fr': {'date': '$d/$m/$Y', 'sernum': 'Tome $SerNum -$$'},
    'es': {'date': '$d/$m/$Y', 'sernum': 'Libro $SerNum -$$'},
    'it': {'date': '$d/$m/$Y', 'sernum': 'Libro $SerNum -$$'},
    'nl': {'date': '$d-$m-$Y', 'sernum': 'Deel $SerNum -$$'},
    'ru': {'date': '$d.$m.$Y', 'sernum': 'Книга $SerNum -$$'},
    'et': {'date': '$d.$m.$Y', 'sernum': 'Raamat $SerNum -$$'},
    'en': {'date': '$d/$m/$Y'},
}

# Country code: name, language and anything the country does differently from its language
COUNTRIES = {
    'SK': {'name': N_('Slovakia'), 'lang': 'sk', 'locale': 'sk_SK.UTF-8'},
    'CZ': {'name': N_('Czech Republic'), 'lang': 'cs', 'locale': 'cs_CZ.UTF-8'},
    'DE': {'name': N_('Germany'), 'lang': 'de', 'locale': 'de_DE.UTF-8'},
    'AT': {'name': N_('Austria'), 'lang': 'de', 'locale': 'de_AT.UTF-8'},
    'CH': {'name': N_('Switzerland'), 'lang': 'de', 'locale': 'de_CH.UTF-8'},
    'PL': {'name': N_('Poland'), 'lang': 'pl', 'locale': 'pl_PL.UTF-8'},
    'FR': {'name': N_('France'), 'lang': 'fr', 'locale': 'fr_FR.UTF-8'},
    'ES': {'name': N_('Spain'), 'lang': 'es', 'locale': 'es_ES.UTF-8'},
    'IT': {'name': N_('Italy'), 'lang': 'it', 'locale': 'it_IT.UTF-8'},
    'NL': {'name': N_('Netherlands'), 'lang': 'nl', 'locale': 'nl_NL.UTF-8'},
    'RU': {'name': N_('Russia'), 'lang': 'ru', 'locale': 'ru_RU.UTF-8'},
    'EE': {'name': N_('Estonia'), 'lang': 'et', 'locale': 'et_EE.UTF-8'},
    'GB': {'name': N_('United Kingdom'), 'lang': 'en', 'locale': 'en_GB.UTF-8', 'codes': ['en-GB']},
    'US': {'name': N_('United States'), 'lang': 'en', 'locale': 'en_US.UTF-8', 'date': '$m/$d/$Y',
           'codes': ['en-US']},
    GENERIC: {'name': N_('Other country'), 'lang': ''},
}

# The country of each language when the browser does not say
LANGUAGE_COUNTRY = {'sk': 'SK', 'cs': 'CZ', 'de': 'DE', 'pl': 'PL', 'fr': 'FR', 'es': 'ES', 'it': 'IT',
                    'nl': 'NL', 'ru': 'RU', 'et': 'EE', 'en': 'GB'}

BOOK_APIS = ['OpenLibrary', 'GoodReads', 'GoogleBooks', 'HardCover', 'DNB', 'BN', 'DBK', 'RanobeDB']
SOURCE_HELP = {
    'DBK_API': N_('Czech and Slovak book database (databazeknih.cz)'),
    'DNB_API': N_('German National Library (Deutsche Nationalbibliothek)'),
    'BN_API': N_('National Library of Poland (Biblioteka Narodowa)'),
}
# Keys whose change needs the page reloaded to show
RELOAD_KEYS = {'UI_LANGUAGE', 'HTTP_LOOK', 'BOOKSTRAP_THEME', 'EBOOK_TAB', 'AUDIO_TAB', 'MAG_TAB', 'COMIC_TAB',
               'SERIES_TAB'}
TAB_KEYS = [('EBOOK_TAB', N_('eBooks')), ('AUDIO_TAB', N_('AudioBooks')), ('MAG_TAB', N_('Magazines')),
            ('COMIC_TAB', N_('Comics')), ('SERIES_TAB', N_('Series'))]
FOLDER_KEYS = [('EBOOK_DIR', N_('eBook library folder')), ('AUDIO_DIR', N_('AudioBook library folder')),
               ('DOWNLOAD_DIR', N_('Download folder'))]


def _config(config):
    if config is None:
        from lazylibrarian.config2 import CONFIG
        return CONFIG
    return config


def _split(value) -> list:
    return [itm.strip() for itm in str(value or '').split(',') if itm.strip()]


def _merge(*lists) -> list:
    """ Concatenate keeping the first of each item, compared without case """
    seen = set()
    result = []
    for lst in lists:
        for itm in lst:
            if itm.lower() not in seen:
                seen.add(itm.lower())
                result.append(itm)
    return result


def _book_codes(lang: str) -> list:
    """ All the codes BOOK_LANGUAGES has for a language """
    for _name, codes in BOOK_LANGUAGES:
        if lang in codes:
            return list(codes)
    return [lang] if lang else []


def _month_locale(lang: str) -> str:
    """ The built-in month name language for a language code, or '' """
    for loc, _name, _months in MONTH_LANGUAGES:
        if loc.split('_')[0].lower() == lang:
            return loc
    return ''


def _parse_tag(tag: str) -> tuple:
    parts = [p for p in str(tag or '').strip().lower().replace('_', '-').split('-') if p]
    if not parts:
        return '', ''
    region = parts[-1] if len(parts) > 1 and len(parts[-1]) == 2 and parts[-1].isalpha() else ''
    return parts[0], region


def guess_country(languages) -> str:
    """ The country for the browser languages, like ['sk-SK', 'en'], the first usable one wins """
    for tag in languages or []:
        lang, region = _parse_tag(tag)
        if region and region.upper() in COUNTRIES:
            return region.upper()
        if lang in LANGUAGE_COUNTRY:
            return LANGUAGE_COUNTRY[lang]
    return GENERIC


def country_choices() -> list:
    """ [{'code', 'label'}] for the country dropdown, sorted by translated name, other country last """
    choices = [{'code': code, 'label': i18n.gettext(info['name'])} for code, info in COUNTRIES.items()
               if code != GENERIC]
    choices.sort(key=lambda c: c['label'].lower())
    choices.append({'code': GENERIC, 'label': i18n.gettext(COUNTRIES[GENERIC]['name'])})
    return choices


def profile(country: str, browser_langs=()) -> dict:
    """ The layered preset for a country: language profile, then the country's own values.
        Another country takes its language from the browser """
    country = country if country in COUNTRIES else GENERIC
    info = COUNTRIES[country]
    lang = info['lang']
    if not lang:
        for tag in browser_langs or []:
            lang = _parse_tag(tag)[0]
            if lang:
                break
    prof = {'country': country, 'lang': lang, 'date': '', 'sernum': '', 'also': [], 'source': '',
            'codes': [], 'locale': ''}
    prof.update(LANGUAGES.get(lang, {}))
    prof.update({k: v for k, v in info.items() if k not in ('name', 'lang')})
    prof['month_locale'] = _month_locale(lang)
    if not prof['locale']:
        prof['locale'] = prof['month_locale']
    return prof


def _row(config, key, label, kind, proposed, choices=None, help_text='', current=None):
    if current is None:
        if kind == 'bool':
            current = config.get_bool(key)
        else:
            current = config.get_str(key)
    return {'key': key, 'label': i18n.gettext(label), 'kind': kind, 'current': current, 'proposed': proposed,
            'choices': choices or [], 'changed': proposed != current,
            'help': i18n.gettext(help_text) if help_text else ''}


def _month_table() -> list:
    return lazylibrarian.MONTHNAMES[0] if lazylibrarian.MONTHNAMES else []


def presets_for(country: str, browser_langs=(), config=None) -> list:
    """ The wizard steps for a country, each {'id', 'title', 'rows'}, every row
        {'key', 'label', 'kind', 'current', 'proposed', 'choices', 'changed', 'help'} """
    config = _config(config)
    prof = profile(country, browser_langs)
    lang = prof['lang']

    ui_langs = ['auto'] + i18n.available_languages()
    ui_proposed = lang if lang in ui_langs and country != GENERIC else 'auto'
    language = [
        _row(config, 'UI_LANGUAGE', N_('Interface language'), 'choice', ui_proposed, ui_langs),
    ]

    sources = [
        _row(config, 'BOOK_API', N_('Main book information source'), 'choice', config.get_str('BOOK_API'),
             BOOK_APIS),
    ]
    if prof['source']:
        sources.append(_row(config, prof['source'], N_('Local book database'), 'bool', True,
                            help_text=SOURCE_HELP.get(prof['source'], '')))
    if country != GENERIC:
        sources.append(_row(config, 'GB_COUNTRY', N_('Country for Google Books results'), 'str', country))

    pref_head = []
    for code in [lang] + prof['also']:
        pref_head += _book_codes(code)
    pref_head += prof['codes'] + _book_codes('en')
    pref = _merge(pref_head, _split(config.get_str('IMP_PREFLANG')))
    langid = _merge(_split(config.get_str('LANGID_LANGUAGES')), [lang] if lang and len(lang) == 2 else [])
    books = [
        _row(config, 'IMP_PREFLANG', N_('Preferred book languages'), 'csv', ', '.join(pref)),
        _row(config, 'LANGID_LANGUAGES', N_('Languages to detect in book files'), 'csv', ', '.join(langid)),
    ]

    dates = []
    month_locale = prof['month_locale']
    if month_locale:
        table = _month_table()
        present = bool(table) and month_locale.lower() in [loc.lower() for loc in table[0]]
        dates.append(_row(config, MONTH_LANGUAGE, N_('Add month names'), 'months', month_locale,
                          current=month_locale if present else ''))
    if prof['locale']:
        dates.append(_row(config, 'DATE_LANG', N_('Language for dates'), 'str', prof['locale']))
    for key, label in (('DATE_FORMAT', N_('Date format')), ('AUTHOR_DATE_FORMAT', N_('Author date format'))):
        dates.append(_row(config, key, label, 'str', prof['date'] or config.get_str(key)))
    if lang:
        dates.append(_row(config, 'PREF_MAGLANG', N_('Preferred magazine language'), 'str', lang))
    words = LANGUAGE_WORDS.get(month_locale, {})
    for key, label in (('ISSUE_NOUNS', N_('Words for issue numbers')),
                       ('VOLUME_NOUNS', N_('Words for volume numbers')),
                       ('MAG_NOUNS', N_('Other words allowed in magazine titles'))):
        current = _split(config.get_str(key))
        dates.append(_row(config, key, label, 'csv', ', '.join(_merge(current, words.get(key.lower(), [])))))

    other = [_row(config, key, label, 'folder', config.get_str(key)) for key, label in FOLDER_KEYS]
    other += [_row(config, key, label, 'bool', config.get_bool(key)) for key, label in TAB_KEYS]
    other.append(_row(config, 'ANNA', N_("Search Anna's Archive"), 'bool', config.get_bool('ANNA')))
    other.append(_row(config, 'BOK', N_('Search Z-Library'), 'bool', config.get_bool('BOK')))
    other.append(_row(config, 'FMT_SERNUM', N_('Series number format'), 'str',
                      prof['sernum'] or config.get_str('FMT_SERNUM')))
    other.append(_row(config, 'HTTP_LOOK', N_('Interface'), 'choice', config.get_str('HTTP_LOOK'),
                      ['bookstrap', 'modern']))
    themes = list(lazylibrarian.BOOKSTRAP_THEMELIST) or [config.get_str('BOOKSTRAP_THEME')]
    other.append(_row(config, 'BOOKSTRAP_THEME', N_('Bookstrap theme'), 'choice',
                      config.get_str('BOOKSTRAP_THEME'), themes))

    return [
        {'id': 'language', 'title': i18n.gettext('Country and language'), 'rows': language},
        {'id': 'sources', 'title': i18n.gettext('Book databases'), 'rows': sources},
        {'id': 'books', 'title': i18n.gettext('Book languages'), 'rows': books},
        {'id': 'dates', 'title': i18n.gettext('Dates, months and magazines'), 'rows': dates},
        {'id': 'other', 'title': i18n.gettext('Library and other settings'), 'rows': other},
    ]


def _all_keys() -> frozenset:
    keys = {MONTH_LANGUAGE, 'UI_LANGUAGE', 'BOOK_API', 'GB_COUNTRY', 'IMP_PREFLANG', 'LANGID_LANGUAGES',
            'DATE_LANG', 'DATE_FORMAT', 'AUTHOR_DATE_FORMAT', 'PREF_MAGLANG', 'ISSUE_NOUNS', 'VOLUME_NOUNS',
            'MAG_NOUNS', 'ANNA', 'BOK', 'FMT_SERNUM', 'HTTP_LOOK', 'BOOKSTRAP_THEME'}
    keys.update(prof['source'] for prof in LANGUAGES.values() if prof.get('source'))
    keys.update(key for key, _label in FOLDER_KEYS + TAB_KEYS)
    return frozenset(keys)


WIZARD_KEYS = _all_keys()
_KIND = {'UI_LANGUAGE': 'choice', 'BOOK_API': 'choice', 'HTTP_LOOK': 'choice', 'ANNA': 'bool', 'BOK': 'bool',
         'DBK_API': 'bool', 'DNB_API': 'bool', 'BN_API': 'bool', MONTH_LANGUAGE: 'months'}
_KIND.update({key: 'bool' for key, _label in TAB_KEYS})
_BOOL_STRINGS = {'1': True, 'true': True, '0': False, 'false': False, '': False}


def _coerce(key: str, value):
    """ The value as the wizard saves it, or raise ValueError """
    kind = _KIND.get(key, 'str')
    if kind == 'bool':
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str) and value.strip().lower() in _BOOL_STRINGS:
            return _BOOL_STRINGS[value.strip().lower()]
        raise ValueError(f'{key}: not a yes/no value')
    if not isinstance(value, str):
        raise ValueError(f'{key}: not text')
    value = value.strip()
    if key == 'UI_LANGUAGE' and value not in ['auto'] + i18n.available_languages():
        raise ValueError(f'{key}: unknown language {value}')
    if key == 'BOOK_API' and value not in BOOK_APIS:
        raise ValueError(f'{key}: unknown source {value}')
    if key == 'HTTP_LOOK' and value not in ('bookstrap', 'modern'):
        raise ValueError(f'{key}: unknown interface {value}')
    if key == MONTH_LANGUAGE and value not in [loc for loc, _n, _m in MONTH_LANGUAGES]:
        raise ValueError(f'{key}: no built-in month names for {value}')
    return value


def _add_month_language(loc: str) -> bool:
    """ Add a built-in language to the month name table, False if it is there already """
    table = _month_table()
    if not table or loc.lower() in [itm.lower() for itm in table[0]]:
        return False
    months = next(m for code, _n, m in MONTH_LANGUAGES if code == loc)
    new_table = copy.deepcopy(table)
    new_table[0] += [loc, loc]
    for idx, (long_name, short_name) in enumerate(months, start=1):
        new_table[idx] += [long_name, short_name]
    from lazylibrarian import common
    return common.save_monthtable(new_table)


def _locale_available(name: str) -> bool:
    try:
        old = locale.setlocale(locale.LC_TIME)
    except locale.Error:
        return True
    try:
        locale.setlocale(locale.LC_TIME, name)
        return True
    except locale.Error:
        return False
    finally:
        with contextlib.suppress(locale.Error):
            locale.setlocale(locale.LC_TIME, old)


def folder_status(path: str) -> str:
    """ ok, missing, not_writable or empty """
    path = str(path or '').strip()
    if not path:
        return 'empty'
    if not os.path.isdir(path):
        return 'missing'
    if not os.access(path, os.W_OK):
        return 'not_writable'
    return 'ok'


def apply(values: dict, config=None) -> dict:
    """ Validate every value first, then set them all and save. Nothing is saved if any value is wrong.
        Returns {'ok', 'changed', 'reload', 'warnings', 'error'} """
    logger = logging.getLogger(__name__)
    config = _config(config)
    result = {'ok': False, 'changed': [], 'reload': False, 'warnings': [], 'error': ''}
    if not isinstance(values, dict):
        result['error'] = 'values must be an object'
        return result
    unknown = sorted(key for key in values if str(key).upper() not in WIZARD_KEYS)
    if unknown:
        result['error'] = i18n.gettext('Not a setting the wizard can change') + ': ' + ', '.join(unknown)
        return result
    clean = {}
    try:
        for key, value in values.items():
            clean[key.upper()] = _coerce(key.upper(), value)
    except ValueError as e:
        result['error'] = str(e)
        return result

    try:
        for key, value in clean.items():
            if key == MONTH_LANGUAGE:
                if _add_month_language(value):
                    result['changed'].append(key)
                continue
            if config.set_from_ui(key, value):
                result['changed'].append(key)
        config.set_bool('SETUP_WIZARD_DONE', True)
        config.save_config_and_backup_old()
    except Exception as e:
        logger.error(f'Setup wizard could not save: {type(e).__name__} {e}')
        result['error'] = str(e)
        return result

    if 'DATE_LANG' in clean and not _locale_available(clean['DATE_LANG']):
        result['warnings'].append(i18n.gettext('The system does not have the locale') + f" {clean['DATE_LANG']}")
    for key, _label in FOLDER_KEYS:
        if clean.get(key) and folder_status(clean[key]) != 'ok':
            result['warnings'].append(i18n.gettext('Folder not found or not writable') + f': {clean[key]}')
    result['reload'] = bool(RELOAD_KEYS & set(result['changed']))
    result['ok'] = True
    logger.info(f"Setup wizard changed {', '.join(result['changed']) or 'nothing'}")
    return result


def dismiss(config=None):
    """ Don't offer the wizard on start again """
    config = _config(config)
    config.set_bool('SETUP_WIZARD_DONE', True)
    config.save_config_and_backup_old()


def should_autoopen(config=None) -> bool:
    """ Offer the wizard on a new install only, an install with a library folder is set up already """
    config = _config(config)
    return not config.get_bool('SETUP_WIZARD_DONE') and not config.get_str('EBOOK_DIR')
