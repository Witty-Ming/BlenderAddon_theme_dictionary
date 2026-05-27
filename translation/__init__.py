import ast
import re

import bpy

from . import en_US, zh_HANS


TRANSLATION_DOMAIN = "theme_dictionary"

langs = {
    "zh_CN": zh_HANS.data,
    "zh_HANS": zh_HANS.data,
    "en_GB": en_US.data,
    "en_US": en_US.data,
}

I18N = {}


def get_language_list():
    try:
        bpy.context.preferences.view.language = ""
    except TypeError as exc:
        matches = re.findall(r"\(([^()]*)\)", exc.args[-1])
        if matches:
            try:
                return ast.literal_eval(f"({matches[-1]})")
            except Exception:
                pass
    return tuple(langs.keys())


def build_translation_dict(data, lang):
    translations = {}
    for source, translated in data.items():
        for context in ("Operator", "*", TRANSLATION_DOMAIN):
            translations.setdefault(lang, {})[(context, source)] = translated
    return translations


def register():
    unregister()
    supported_languages = set(get_language_list())
    translations = {}
    for lang_code, data in langs.items():
        if lang_code not in supported_languages:
            continue
        for lang, entries in build_translation_dict(data, lang_code).items():
            translations.setdefault(lang, {}).update(entries)
    if not translations:
        return
    try:
        bpy.app.translations.register(TRANSLATION_DOMAIN, translations)
        I18N[TRANSLATION_DOMAIN] = translations
    except ValueError:
        pass


def unregister():
    if not I18N:
        return
    try:
        bpy.app.translations.unregister(TRANSLATION_DOMAIN)
    except Exception:
        pass
    I18N.clear()
