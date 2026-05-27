bl_info = {
    "name": "theme dictionary",
    "author": "61+",
    "version": (0, 6, 4),
    "blender": (5, 0, 0),
    "location": "Top Bar / Alt+C",
    "description": "Search for related theme color entries based on color or mouse area",
    "category": "Interface",
}

import colorsys
import json
import math
import os
import tempfile
import time

import bpy
from bpy.app.translations import pgettext, pgettext_iface as iface
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatVectorProperty, IntProperty, StringProperty
from bpy.types import AddonPreferences, Menu, Operator, PropertyGroup, UIList

try:
    from . import translation
except Exception:
    translation = None


ADDON_ID = __name__
BOUNDARY_THRESHOLD = 12
POPUP_WIDTH = 300
POPUP_LIST_ROWS = 12
HISTORY_TIMER_INTERVAL = 0.35
SIMILAR_TOLERANCE_DEFAULT = 16
FALLBACK_MATCH_TOLERANCE = 40
AREA_SAMPLE_RADIUS = 1
AREA_COLOR_MATCH_TOLERANCE = 52
AREA_DIRECT_MATCH_TOLERANCE = 34
AREA_NEARBY_REGION_RADIUS = 6
LEARNING_MATCH_TOLERANCE = 54
LEARNING_STORE_LIMIT = 600
CANDIDATE_PREVIEW_DELAY = 0.0
CANDIDATE_PREVIEW_INTERVAL = 0.04
CANDIDATE_PREVIEW_CYCLE = 1.0
CANDIDATE_PREVIEW_VALUE_AMPLITUDE = 0.60
addon_keymaps = []
_theme_snapshot = None
_theme_history = []
_theme_redo_history = []
_last_theme_state = None
_last_theme_token = None
_history_timer_running = False
_suspend_history = False
_pending_history_before = None
_pending_history_after = None
_pending_history_last_change_time = 0.0
_pending_history_token = None
_pending_history_is_similar_sync = False
_history_commit_delay = 0.8
_probe_runtime = {}
_similar_seed_candidates = []
_similar_seed_signature = None
_similar_seed_path = ""
_sample_refresh_pending = False
_sample_refresh_time = 0.0
_sample_refresh_timer_running = False
_syncing_similar_colors = False
_candidate_preview_path = ""
_candidate_preview_original = None
_candidate_preview_last_written = None
_candidate_preview_start_time = 0.0
_candidate_preview_last_draw_time = 0.0
_candidate_preview_timer_running = False
_candidate_preview_auto_disabled_sync = False
_locked_candidate_paths = set()
_learning_cache = None


PROBE_MODE_ITEMS = (
    ("AREA", "Area Detect", "Detect theme colors from the area under the mouse"),
    ("SIMILAR", "Similar Color", "Search globally for colors similar to the current sample"),
)


SEMANTIC_MAP = {
    "GLOBAL_BOUNDARY": [
        ("Panel Border", "user_interface.wcol_regular.outline"),
        ("Tool Border", "user_interface.wcol_tool.outline"),
        ("Menu Border", "user_interface.wcol_menu.outline"),
        ("Tooltip Border", "user_interface.wcol_tooltip.outline"),
        ("List Item Border", "user_interface.wcol_list_item.outline"),
    ],
    "MENU_UI": [
        ("Menu Background", "user_interface.wcol_menu.inner"),
        ("Menu Text", "user_interface.wcol_menu.text"),
        ("Menu Highlight", "user_interface.wcol_menu.item"),
        ("Menu Border", "user_interface.wcol_menu.outline"),
        ("Tooltip Background", "user_interface.wcol_tooltip.inner"),
        ("Tooltip Text", "user_interface.wcol_tooltip.text"),
    ],
    "PANEL_UI": [
        ("Panel Background", "user_interface.wcol_panel.inner"),
        ("Panel Header", "user_interface.wcol_panel.item"),
        ("Panel Text", "user_interface.wcol_panel.text"),
        ("Box Background", "user_interface.wcol_box.inner"),
        ("Active Tab", "user_interface.wcol_tab.item"),
        ("Tab Background", "user_interface.wcol_tab.inner"),
        ("Regular Button", "user_interface.wcol_regular.inner"),
        ("Active Button", "user_interface.wcol_regular.item"),
        ("Value Slider", "user_interface.wcol_num.inner"),
        ("Tool Button Background", "user_interface.wcol_tool.inner"),
        ("Active Tool Button", "user_interface.wcol_tool.item"),
        ("Tool Button Text", "user_interface.wcol_tool.text"),
    ],
    "VIEW_3D_PANEL": [
        ("3D Sidebar Background", "view_3d.space.panelcolors.back"),
        ("3D Sidebar Header", "view_3d.space.panelcolors.header"),
        ("3D Sidebar Sub Background", "view_3d.space.panelcolors.sub_back"),
    ],
    "VIEW_3D_EDIT": [
        ("Edit Vertex", "view_3d.vertex"),
        ("Selected Vertex", "view_3d.vertex_select"),
        ("Active Vertex", "view_3d.vertex_active"),
        ("Edit Wire", "view_3d.wire_edit"),
        ("Selected Edge", "view_3d.edge_select"),
        ("Face Selection Edge", "view_3d.edge_facesel"),
        ("Seam Edge", "view_3d.edge_seam"),
        ("Sharp Edge", "view_3d.edge_sharp"),
        ("Crease Edge", "view_3d.edge_crease"),
        ("Bevel Edge", "view_3d.edge_bevel"),
        ("Edit Face", "view_3d.face"),
        ("Selected Face", "view_3d.face_select"),
        ("Face Dot", "view_3d.face_dot"),
    ],
    "VIEW_3D": [
        ("3D View Gradient Top", "view_3d.space.gradients.high_gradient"),
        ("3D View Gradient Bottom", "view_3d.space.gradients.gradient"),
        ("Object Wireframe", "view_3d.wire"),
        ("3D Grid", "view_3d.grid"),
        ("3D Major Grid", "view_3d.grid_major"),
        ("3D Axis X", "user_interface.axis_x"),
        ("3D Axis Y", "user_interface.axis_y"),
        ("3D Axis Z", "user_interface.axis_z"),
        ("Selected Object Outline", "view_3d.object_selected"),
        ("Active Object Highlight", "view_3d.object_active"),
        ("3D Title Text", "view_3d.space.title"),
        ("3D Panel Header", "view_3d.space.header"),
        ("3D Panel Text", "view_3d.space.text"),
        ("3D Highlighted Text", "view_3d.space.text_hi"),
    ],
    "PROPERTIES": [
        ("Properties Background", "properties.space.back"),
        ("Properties Header", "properties.space.header"),
        ("Properties Text", "properties.space.text"),
        ("Properties Highlighted Text", "properties.space.text_hi"),
        ("Regular Button", "user_interface.wcol_regular.inner"),
        ("Regular Button Text", "user_interface.wcol_regular.text"),
    ],
    "OUTLINER": [
        ("Outliner Background", "outliner.space.back"),
        ("Outliner Header", "outliner.space.header"),
        ("Outliner Text", "outliner.space.text"),
        ("Outliner Highlighted Text", "outliner.space.text_hi"),
        ("Outliner Row Highlight", "outliner.match"),
    ],
    "NODE_EDITOR": [
        ("Node Background", "node_editor.space.back"),
        ("Node Header", "node_editor.space.header"),
        ("Node Text", "node_editor.space.text"),
        ("Node Highlighted Text", "node_editor.space.text_hi"),
        ("Node Grid", "node_editor.grid"),
        ("Node Link", "node_editor.wire"),
    ],
}


SHORTCUT_MAP_TYPES = (
    ("KEYBOARD", "Keyboard", "Use a keyboard shortcut"),
    ("MOUSE", "Mouse", "Use a mouse shortcut"),
)


def bilingual_tooltip(english, chinese):
    return english


def tr(text):
    if not text:
        return text
    translated = pgettext(text, msgctxt="theme_dictionary")
    if translated != text:
        return translated
    return iface(text)


THEME_PATH_LABELS_EN = {
    "user_interface.wcol_regular.outline": "Panel Border",
    "user_interface.wcol_tool.outline": "Tool Border",
    "user_interface.wcol_menu.outline": "Menu Border",
    "user_interface.wcol_tooltip.outline": "Tooltip Border",
    "user_interface.wcol_list_item.outline": "List Item Border",
    "user_interface.wcol_menu.inner": "Menu Background",
    "user_interface.wcol_menu.text": "Menu Text",
    "user_interface.wcol_menu.item": "Menu Highlight",
    "user_interface.wcol_panel.inner": "Panel Background",
    "user_interface.wcol_panel.item": "Panel Header",
    "user_interface.wcol_panel.text": "Panel Text",
    "user_interface.wcol_box.inner": "Box Background",
    "user_interface.wcol_tab.item": "Active Tab",
    "user_interface.wcol_tab.inner": "Tab Background",
    "user_interface.wcol_regular.inner": "Regular Button",
    "user_interface.wcol_regular.item": "Active Button",
    "user_interface.wcol_regular.text": "Regular Button Text",
    "user_interface.wcol_num.inner": "Value Slider",
    "user_interface.wcol_tool.inner": "Tool Button Background",
    "user_interface.wcol_tool.item": "Active Tool Button",
    "user_interface.wcol_tool.text": "Tool Button Text",
    "view_3d.space.panelcolors.back": "3D Sidebar Background",
    "view_3d.space.panelcolors.header": "3D Sidebar Header",
    "view_3d.space.panelcolors.sub_back": "3D Sidebar Sub Background",
    "view_3d.vertex": "Edit Vertex",
    "view_3d.vertex_select": "Selected Vertex",
    "view_3d.vertex_active": "Active Vertex",
    "view_3d.wire_edit": "Edit Wire",
    "view_3d.edge_select": "Selected Edge",
    "view_3d.edge_facesel": "Face Selection Edge",
    "view_3d.edge_seam": "Seam Edge",
    "view_3d.edge_sharp": "Sharp Edge",
    "view_3d.edge_crease": "Crease Edge",
    "view_3d.edge_bevel": "Bevel Edge",
    "view_3d.face": "Edit Face",
    "view_3d.face_select": "Selected Face",
    "view_3d.face_dot": "Face Dot",
    "view_3d.space.gradients.high_gradient": "3D View Gradient Top",
    "view_3d.space.gradients.gradient": "3D View Gradient Bottom",
    "view_3d.wire": "Object Wireframe",
    "view_3d.grid": "3D Grid",
    "view_3d.grid_major": "3D Major Grid",
    "user_interface.axis_x": "3D Axis X",
    "user_interface.axis_y": "3D Axis Y",
    "user_interface.axis_z": "3D Axis Z",
    "view_3d.object_selected": "Selected Object Outline",
    "view_3d.object_active": "Active Object Highlight",
    "view_3d.space.title": "3D Title Text",
    "view_3d.space.header": "3D Panel Header",
    "view_3d.space.text": "3D Panel Text",
    "view_3d.space.text_hi": "3D Highlighted Text",
    "properties.space.back": "Properties Background",
    "properties.space.header": "Properties Header",
    "properties.space.text": "Properties Text",
    "properties.space.text_hi": "Properties Highlighted Text",
    "outliner.space.back": "Outliner Background",
    "outliner.space.header": "Outliner Header",
    "outliner.space.text": "Outliner Text",
    "outliner.space.text_hi": "Outliner Highlighted Text",
    "outliner.match": "Outliner Row Highlight",
    "node_editor.space.back": "Node Background",
    "node_editor.space.header": "Node Header",
    "node_editor.space.text": "Node Text",
    "node_editor.space.text_hi": "Node Highlighted Text",
    "node_editor.grid": "Node Grid",
    "node_editor.wire": "Node Link",
}


THEME_ROOT_LABELS_EN = {
    "bone_color_sets": "Bone Color Set",
    "clip_editor": "Movie Clip Editor",
    "collection_color": "Collection Color",
    "common": "Common",
    "console": "Python Console",
    "dopesheet_editor": "Dope Sheet",
    "file_browser": "File Browser",
    "graph_editor": "Graph Editor",
    "image_editor": "Image Editor",
    "info": "Info",
    "nla_editor": "Nonlinear Animation",
    "node_editor": "Node Editor",
    "outliner": "Outliner",
    "preferences": "Preferences",
    "properties": "Properties",
    "regions": "Regions",
    "sequence_editor": "Video Sequencer",
    "spreadsheet": "Spreadsheet",
    "statusbar": "Status Bar",
    "strip_color": "Strip Color Tag",
    "text_editor": "Text Editor",
    "topbar": "Top Bar",
    "user_interface": "User Interface",
    "view_3d": "3D Viewport",
}


THEME_PATH_ALIASES = {
    "user_interface.wcol_panel.inner": "user_interface.panel_back",
    "user_interface.wcol_panel.item": "user_interface.panel_header",
    "user_interface.wcol_panel.text": "user_interface.panel_text",
    "view_3d.space.panelcolors.back": "user_interface.panel_back",
    "view_3d.space.panelcolors.header": "user_interface.panel_header",
    "view_3d.space.panelcolors.sub_back": "user_interface.panel_sub_back",
    "view_3d.vertex_active": "view_3d.editmesh_active",
    "view_3d.edge_facesel": "view_3d.edge_select",
    "view_3d.edge_seam": "view_3d.seam",
    "view_3d.edge_sharp": "view_3d.sharp",
    "view_3d.edge_crease": "view_3d.crease",
    "view_3d.edge_bevel": "view_3d.bevel",
    "view_3d.face_dot": "view_3d.face_mode_select",
}


AREA_THEME_ROOTS = {
    "CLIP_EDITOR": "clip_editor",
    "CONSOLE": "console",
    "DOPESHEET_EDITOR": "dopesheet_editor",
    "FILE_BROWSER": "file_browser",
    "GRAPH_EDITOR": "graph_editor",
    "IMAGE_EDITOR": "image_editor",
    "INFO": "info",
    "NLA_EDITOR": "nla_editor",
    "NODE_EDITOR": "node_editor",
    "OUTLINER": "outliner",
    "PREFERENCES": "preferences",
    "PROPERTIES": "properties",
    "SEQUENCE_EDITOR": "sequence_editor",
    "SPREADSHEET": "spreadsheet",
    "STATUSBAR": "statusbar",
    "TEXT_EDITOR": "text_editor",
    "TOPBAR": "topbar",
    "VIEW_3D": "view_3d",
}


COMMON_PREFIXES_BY_AREA = {
    "DOPESHEET_EDITOR": ("common.anim",),
    "GRAPH_EDITOR": ("common.anim", "common.curves"),
    "NLA_EDITOR": ("common.anim",),
    "SEQUENCE_EDITOR": ("common.anim", "strip_color"),
    "OUTLINER": ("collection_color",),
    "VIEW_3D": ("common.curves", "bone_color_sets"),
}


PANEL_COLOR_PREFIXES = (
    "regions.sidebars",
    "user_interface.panel_header",
    "user_interface.panel_title",
    "user_interface.panel_text",
    "user_interface.panel_back",
    "user_interface.panel_sub_back",
    "user_interface.panel_outline",
    "user_interface.panel_active",
    "user_interface.wcol_panel",
    "user_interface.wcol_box",
    "user_interface.wcol_tab",
    "user_interface.wcol_regular",
    "user_interface.wcol_num",
    "user_interface.wcol_numslider",
)


HEADER_COLOR_PREFIXES = (
    "user_interface.wcol_menu",
    "user_interface.wcol_menu_item",
    "user_interface.wcol_pulldown",
    "user_interface.wcol_regular",
    "user_interface.editor_border",
    "user_interface.editor_outline",
    "user_interface.editor_outline_active",
)


TOOL_COLOR_PREFIXES = (
    "user_interface.wcol_tool",
    "user_interface.wcol_toolbar_item",
    "user_interface.wcol_regular",
    "user_interface.editor_border",
)


def prettify_identifier(identifier):
    aliases = {
        "wcol": "Widget",
        "wcol_box": "Box",
        "wcol_curve": "Curve",
        "wcol_list_item": "List Item",
        "wcol_menu": "Menu",
        "wcol_menu_back": "Menu Back",
        "wcol_menu_item": "Menu Item",
        "wcol_num": "Number",
        "wcol_numslider": "Value Slider",
        "wcol_option": "Option",
        "wcol_pie_menu": "Pie Menu",
        "wcol_progress": "Progress",
        "wcol_pulldown": "Pulldown",
        "wcol_radio": "Radio",
        "wcol_regular": "Regular",
        "wcol_scroll": "Scroll",
        "wcol_state": "State",
        "wcol_tab": "Tab",
        "wcol_text": "Text",
        "wcol_toggle": "Toggle",
        "wcol_tool": "Tool",
        "wcol_toolbar_item": "Toolbar Item",
        "wcol_tooltip": "Tooltip",
        "panelcolors": "Panel Colors",
        "metadatabg": "Metadata Background",
        "metadatatext": "Metadata Text",
        "sub_back": "Sub Back",
        "text_hi": "Text Highlight",
        "text_sel": "Selected Text",
        "header_text": "Header Text",
        "header_text_hi": "Header Text Highlight",
        "header_back": "Header Back",
        "inner_sel": "Inner Selected",
        "inner_anim": "Animated Inner",
        "inner_anim_sel": "Selected Animated Inner",
        "inner_changed": "Changed Inner",
        "inner_changed_sel": "Selected Changed Inner",
        "inner_driven": "Driven Inner",
        "inner_driven_sel": "Selected Driven Inner",
        "inner_key": "Keyed Inner",
        "inner_key_sel": "Selected Keyed Inner",
        "inner_overridden": "Overridden Inner",
        "inner_overridden_sel": "Selected Overridden Inner",
        "item_sel": "Item Selected",
        "outline_sel": "Outline Selected",
        "tab_active": "Tab Active",
        "tab_inactive": "Tab Inactive",
        "tab_back": "Tab Back",
        "tab_outline": "Tab Outline",
        "editor_outline_active": "Editor Outline Active",
        "edge_facesel": "Edge Facesel",
        "edge_mode_select": "Edge Mode Select",
        "object_selected": "Object Selected",
        "object_active": "Object Active",
        "grid_major": "Grid Major",
        "high_gradient": "High Gradient",
        "channel_group_active": "Active Channel Group",
        "channel_selected": "Selected Channel",
        "channels_sub": "Sub Channels",
        "keyframe_breakdown": "Keyframe Breakdown",
        "keyframe_breakdown_selected": "Selected Keyframe Breakdown",
        "keyframe_extreme": "Keyframe Extreme",
        "keyframe_extreme_selected": "Selected Keyframe Extreme",
        "keyframe_generated": "Generated Keyframe",
        "keyframe_generated_selected": "Selected Generated Keyframe",
        "keyframe_jitter": "Keyframe Jitter",
        "keyframe_jitter_selected": "Selected Keyframe Jitter",
        "keyframe_moving_hold": "Moving Hold Keyframe",
        "keyframe_moving_hold_selected": "Selected Moving Hold Keyframe",
        "handle_align": "Aligned Handle",
        "handle_auto": "Automatic Handle",
        "handle_auto_clamped": "Auto Clamped Handle",
        "handle_free": "Free Handle",
        "handle_sel_align": "Selected Aligned Handle",
        "handle_sel_auto": "Selected Automatic Handle",
        "handle_sel_auto_clamped": "Selected Auto Clamped Handle",
        "handle_sel_free": "Selected Free Handle",
        "handle_sel_vect": "Selected Vector Handle",
        "handle_vect": "Vector Handle",
        "anim_interpolation_constant": "Constant Animation Interpolation",
        "anim_interpolation_linear": "Linear Animation Interpolation",
        "anim_interpolation_other": "Other Animation Interpolation",
        "editmesh_active": "Active Edit Mesh",
        "face_mode_select": "Face Mode Select",
        "preview_stitch_active": "Active Stitch Preview",
        "preview_stitch_edge": "Stitch Preview Edge",
        "preview_stitch_face": "Stitch Preview Face",
        "preview_stitch_stitchable": "Stitchable Stitch Preview",
        "preview_stitch_unstitchable": "Unstitchable Stitch Preview",
        "preview_stitch_vert": "Stitch Preview Vertex",
        "scope_back": "Scope Background",
        "uv_shadow": "UV Shadow",
        "info_debug": "Debug Info",
        "info_debug_text": "Debug Info Text",
        "info_error_text": "Error Info Text",
        "info_info_text": "Info Text",
        "info_operator": "Operator Info",
        "info_operator_text": "Operator Info Text",
        "info_property": "Property Info",
        "info_property_text": "Property Info Text",
        "info_selected": "Selected Info",
        "info_selected_text": "Selected Info Text",
        "info_warning_text": "Warning Info Text",
        "active_action_unset": "Unset Active Action",
        "transition_strips": "Transition Strips",
        "transition_strips_selected": "Selected Transition Strips",
        "tweak_duplicate": "Tweak Duplicate",
        "distor_node": "Distort Node",
        "foreach_geometry_element_zone": "For Each Geometry Element Zone",
        "node_active": "Active Node",
        "wire_inner": "Wire Inner",
        "time_marker": "Time Marker",
        "time_marker_selected": "Selected Time Marker",
        "movieclip_strip": "Movie Clip Strip",
        "preview_back": "Preview Background",
        "selected_strip": "Selected Strip",
        "axis_w": "Axis W",
        "gizmo_hi": "Gizmo Highlight",
        "icon_autokey": "Autokey Icon",
        "icon_collection": "Collection Icon",
        "icon_modifier": "Modifier Icon",
        "icon_object": "Object Icon",
        "icon_object_data": "Object Data Icon",
        "icon_scene": "Scene Icon",
        "icon_shading": "Shading Icon",
        "transparent_checker_primary": "Primary Transparent Checker",
        "transparent_checker_secondary": "Secondary Transparent Checker",
        "widget_text_cursor": "Widget Text Cursor",
        "clipping_border_3d": "3D Clipping Border",
        "extra_edge_angle": "Extra Edge Angle",
        "extra_edge_len": "Extra Edge Length",
        "extra_face_angle": "Extra Face Angle",
        "extra_face_area": "Extra Face Area",
        "face_back": "Face Back",
        "face_front": "Face Front",
        "freestyle": "Freestyle",
        "gp_vertex": "Grease Pencil Vertex",
        "gp_vertex_select": "Selected Grease Pencil Vertex",
        "gp_wire_edit": "Grease Pencil Edit Wire",
        "nurb_sel_uline": "Selected NURBS U Line",
        "nurb_sel_vline": "Selected NURBS V Line",
        "nurb_uline": "NURBS U Line",
        "nurb_vline": "NURBS V Line",
        "text_grease_pencil": "Grease Pencil Text",
        "vertex_unreferenced": "Unreferenced Vertex",
    }
    return aliases.get(identifier, identifier.replace("_", " ").title())


def theme_segment_base_and_index(segment):
    if "[" not in segment:
        return segment, None
    base, rest = segment.split("[", 1)
    close_index = rest.find("]")
    if close_index < 0:
        return base, None
    try:
        return base, int(rest[:close_index])
    except Exception:
        return base, None


def theme_segment_label(segment):
    base, index = theme_segment_base_and_index(segment)
    label = THEME_ROOT_LABELS_EN.get(base, prettify_identifier(base))
    if index is not None:
        return f"{label} {index + 1}"
    return label


def localized_theme_segment_label(segment):
    base, index = theme_segment_base_and_index(segment)
    label = tr(THEME_ROOT_LABELS_EN.get(base, prettify_identifier(base)))
    if index is not None:
        return f"{label} {index + 1}"
    return label


def localized_identifier_label(identifier):
    label = prettify_identifier(identifier)
    translated = tr(label)
    if translated != label:
        return translated
    words = label.split()
    translated_words = [tr(word) for word in words]
    if translated_words != words:
        return "".join(translated_words)
    return translated


def readable_theme_path_label(path):
    if not path:
        return ""
    parts = path.split(".")
    root_label = theme_segment_label(parts[0])
    tail = prettify_identifier(theme_segment_base_and_index(parts[-1])[0])
    parents = [
        prettify_identifier(theme_segment_base_and_index(part)[0])
        for part in parts[1:-1]
        if theme_segment_base_and_index(part)[0] not in {"space"}
    ]
    if parents:
        return f"{root_label} {' '.join(parents[-2:])}: {tail}"
    return f"{root_label}: {tail}"


def localized_readable_theme_path_label(path):
    if not path:
        return ""
    parts = path.split(".")
    root_label = localized_theme_segment_label(parts[0])
    root_english = theme_segment_label(parts[0])
    tail_english = prettify_identifier(theme_segment_base_and_index(parts[-1])[0])
    parents_english = [
        prettify_identifier(theme_segment_base_and_index(part)[0])
        for part in parts[1:-1]
        if theme_segment_base_and_index(part)[0] not in {"space"}
    ]
    if not parents_english:
        combined = tr(f"{root_english} {tail_english}")
        if combined != f"{root_english} {tail_english}":
            return combined

    tail = localized_identifier_label(theme_segment_base_and_index(parts[-1])[0])
    parents = [
        localized_identifier_label(theme_segment_base_and_index(part)[0])
        for part in parts[1:-1]
        if theme_segment_base_and_index(part)[0] not in {"space"}
    ]
    if parents:
        return f"{root_label} {' '.join(parents[-2:])}: {tail}"
    return f"{root_label}: {tail}"


def english_theme_label(label, path):
    path = canonical_theme_path(path)
    if path.endswith(".background_type"):
        return "Background Type"
    if path in THEME_PATH_LABELS_EN:
        return THEME_PATH_LABELS_EN[path]
    if label and label != path.rsplit(".", 1)[-1]:
        return label
    fallback = readable_theme_path_label(path)
    if fallback:
        return fallback
    tail = path.rsplit(".", 1)[-1]
    return tail.replace("_", " ").title() if tail else label


def localized_theme_label(label, path):
    english_label = english_theme_label(label, path)
    localized_label = tr(english_label)
    if localized_label != english_label:
        return localized_label
    fallback = localized_readable_theme_path_label(canonical_theme_path(path))
    return fallback or localized_label


def theme_root():
    prefs = bpy.context.preferences
    themes = getattr(prefs, "themes", None)
    if not themes:
        return None
    try:
        return themes[0]
    except Exception:
        return None


def iter_collection_items(collection, path):
    try:
        for index, item in enumerate(collection):
            yield item, f"{path}[{index}]"
    except Exception:
        return


def iter_theme_paths(base, prefix=""):
    if base is None:
        return
    rna = getattr(base, "bl_rna", None)
    if rna is None:
        return
    for prop in rna.properties:
        ident = prop.identifier
        if ident == "rna_type":
            continue
        try:
            value = getattr(base, ident)
        except Exception:
            continue
        path = f"{prefix}.{ident}" if prefix else ident
        ptype = getattr(prop, "type", "")
        subtype = getattr(prop, "subtype", "")
        is_color = (
            ptype in {"FLOAT", "INT"}
            and getattr(prop, "is_array", False)
            and getattr(prop, "array_length", 0) in {3, 4}
            and subtype in {"COLOR", "COLOR_GAMMA"}
        )
        if is_color and not prop.is_readonly:
            yield path, value
        elif ptype == "POINTER" and value is not None:
            yield from iter_theme_paths(value, path)
        elif ptype == "COLLECTION" and value is not None:
            for item, item_path in iter_collection_items(value, path):
                yield from iter_theme_paths(item, item_path)


def iter_theme_mode_color_groups(base=None, prefix=""):
    if base is None:
        base = theme_root()
    if base is None:
        return
    rna = getattr(base, "bl_rna", None)
    if rna is None:
        return

    enum_props = []
    color_props = []
    child_props = []
    for prop in rna.properties:
        ident = prop.identifier
        if ident == "rna_type":
            continue
        try:
            value = getattr(base, ident)
        except Exception:
            continue
        path = f"{prefix}.{ident}" if prefix else ident
        ptype = getattr(prop, "type", "")
        subtype = getattr(prop, "subtype", "")
        is_color = (
            ptype in {"FLOAT", "INT"}
            and getattr(prop, "is_array", False)
            and getattr(prop, "array_length", 0) in {3, 4}
            and subtype in {"COLOR", "COLOR_GAMMA"}
        )
        if ptype == "ENUM" and not prop.is_readonly:
            enum_props.append({"label": prop.name or ident, "path": path})
        elif is_color and not prop.is_readonly:
            color_props.append({"label": prop.name or ident, "path": path})
        elif ptype == "POINTER" and value is not None:
            child_props.append((value, path))
        elif ptype == "COLLECTION" and value is not None:
            child_props.extend(iter_collection_items(value, path))

    if enum_props and color_props:
        yield {
            "label": getattr(rna, "name", "") or prefix.split(".")[-1],
            "prefix": prefix,
            "enums": enum_props,
            "colors": color_props,
        }
    for value, path in child_props:
        yield from iter_theme_mode_color_groups(value, path)


def build_theme_index():
    root = theme_root()
    if root is None:
        return {}
    return {path: value for path, value in iter_theme_paths(root)}


def canonical_theme_path(path, theme_index=None):
    if theme_index is not None and path in theme_index:
        return path
    return THEME_PATH_ALIASES.get(path, path)


def build_mode_color_groups():
    return list(iter_theme_mode_color_groups())


class ThemeFieldScanner:
    @staticmethod
    def scan():
        return build_theme_index()


def resolve_theme_path(path):
    root = theme_root()
    if root is None or not path:
        return None, None
    path = canonical_theme_path(path)
    current = root
    parts = path.split(".")
    for attr in parts[:-1]:
        current = resolve_theme_path_segment(current, attr)
        if current is None:
            return None, None
    attr = parts[-1]
    if not hasattr(current, attr):
        return None, None
    return current, attr


def resolve_theme_path_segment(base, segment):
    if base is None or not segment:
        return None
    if "[" not in segment:
        if not hasattr(base, segment):
            return None
        return getattr(base, segment)

    attr, rest = segment.split("[", 1)
    if not hasattr(base, attr):
        return None
    current = getattr(base, attr)
    rest = "[" + rest
    while rest:
        if not rest.startswith("["):
            return None
        close_index = rest.find("]")
        if close_index <= 1:
            return None
        try:
            item_index = int(rest[1:close_index])
            current = current[item_index]
        except Exception:
            return None
        rest = rest[close_index + 1:]
    return current


def color_to_list(value):
    try:
        return [float(channel) for channel in value]
    except Exception:
        return None


def clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, value))


def clamp_hsv_triplet(hue, sat, val):
    return (
        clamp(hue, 0.0, 1.0),
        clamp(sat, 0.0, 1.0),
        clamp(val, 0.0, 1.0),
    )


def color_signature(value):
    color = color_to_list(value)
    if color is None:
        return None
    return tuple(max(0, min(255, int(round(channel * 255)))) for channel in color)


def signature_from_color(color):
    try:
        channels = list(color)
    except Exception:
        return None
    if len(channels) < 3:
        return None
    return tuple(max(0, min(255, int(round(channel * 255)))) for channel in channels[:4])


def color_from_signature(signature):
    if signature is None or len(signature) < 3:
        return None
    alpha = signature[3] if len(signature) >= 4 else 255
    return tuple(channel / 255.0 for channel in (signature[0], signature[1], signature[2], alpha))


def color_priority(color):
    red, green, blue = color[:3]
    hue, sat, val = colorsys.rgb_to_hsv(red, green, blue)
    return sat * 3.2 + abs(val - 0.5) * 0.25 + val * 0.08


def append_sample_log(message):
    log_path = os.path.join(tempfile.gettempdir(), "theme_probe_sample_debug.log")
    try:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%H:%M:%S')} {message}\n")
    except Exception:
        pass


def pixel_color_at(pixels, width, height, x, y):
    px = max(0, min(width - 1, int(x)))
    py = max(0, min(height - 1, int(y)))
    index = (py * width + px) * 4
    color = tuple(pixels[index:index + 4])
    return color if len(color) == 4 else None


def best_color_around(pixels, width, height, center_x, center_y, radius):
    best = None
    best_score = -1e9
    cx = max(0, min(width - 1, int(center_x)))
    cy = max(0, min(height - 1, int(center_y)))
    center = pixel_color_at(pixels, width, height, cx, cy) or (0.0, 0.0, 0.0, 1.0)
    for py in range(max(0, cy - radius), min(height, cy + radius + 1)):
        for px in range(max(0, cx - radius), min(width, cx + radius + 1)):
            index = (py * width + px) * 4
            color = tuple(pixels[index:index + 4])
            if len(color) != 4:
                continue
            distance = abs(px - cx) + abs(py - cy)
            score = color_priority(color) * 10.0 - distance * 0.2 - sum(abs(color[i] - center[i]) for i in range(3)) * 0.25
            if score > best_score:
                best_score = score
                best = color
    return best, best_score


def sample_screen_color(context, mouse_x, mouse_y, radius=5, center_weight=0.0, exact_pointer=False):
    filepath = os.path.join(tempfile.gettempdir(), "theme_probe_sample.png")
    image = None
    try:
        bpy.ops.screen.screenshot(filepath=filepath)
        image = bpy.data.images.load(filepath, check_existing=False)
        width, height = image.size
        if width <= 0 or height <= 0:
            return None

        win_w = max(1, int(getattr(context.window, "width", 1)))
        win_h = max(1, int(getattr(context.window, "height", 1)))
        scale_x = width / float(win_w)
        scale_y = height / float(win_h)
        append_sample_log(
            f"window={win_w}x{win_h} image={width}x{height} mouse=({mouse_x},{mouse_y}) scale=({scale_x:.3f},{scale_y:.3f})"
        )

        pixels = image.pixels[:]
        x_scaled = int(mouse_x * scale_x)
        y_scaled = int(mouse_y * scale_y)
        if exact_pointer:
            exact_x = max(0, min(width - 1, x_scaled))
            exact_y = max(0, min(height - 1, height - 1 - y_scaled))
            exact_color = pixel_color_at(pixels, width, height, exact_x, exact_y)
            append_sample_log(f"exact_pointer point=({exact_x},{exact_y}) color={exact_color}")
            return exact_color

        candidates = [
            (x_scaled, height - 1 - y_scaled, "scaled_flip"),
            (x_scaled, y_scaled, "scaled_raw"),
            (int(mouse_x), height - 1 - int(mouse_y), "raw_flip"),
            (int(mouse_x), int(mouse_y), "raw_raw"),
        ]
        best_color = None
        best_score = -1e9
        best_tag = ""
        for cx, cy, tag in candidates:
            color, score = best_color_around(pixels, width, height, cx, cy, radius)
            center_color = pixel_color_at(pixels, width, height, cx, cy)
            if center_color is not None and center_weight:
                center_score = color_priority(center_color) * 10.0 + center_weight
                if center_score > score:
                    color = center_color
                    score = center_score
                    tag = f"{tag}_center"
            append_sample_log(f"candidate={tag} point=({cx},{cy}) score={score:.3f} color={color}")
            if color is not None and score > best_score:
                best_score = score
                best_color = color
                best_tag = tag
        append_sample_log(f"selected={best_tag} score={best_score:.3f} color={best_color}")
        return best_color
    except Exception as exc:
        print(f"Theme Probe screen sample failed: {exc}")
        append_sample_log(f"sample_failed: {exc}")
        return None
    finally:
        if image is not None:
            try:
                bpy.data.images.remove(image)
            except Exception:
                pass
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass


def color_hex(signature):
    if signature is None:
        return ""
    if len(signature) >= 4:
        return "#{:02X}{:02X}{:02X}{:02X}".format(*signature[:4])
    if len(signature) >= 3:
        return "#{:02X}{:02X}{:02X}".format(*signature[:3])
    return ""


def color_tolerance_distance(first, second):
    if first is None or second is None:
        return None
    channels = min(len(first), len(second))
    if channels == 0:
        return None
    return max(abs(first[index] - second[index]) for index in range(channels))


def color_match_distance(signature, seed_signature, tolerance):
    if signature is None or seed_signature is None:
        return None
    if len(signature) < 3 or len(seed_signature) < 3:
        return None

    rgb_delta = max(abs(signature[index] - seed_signature[index]) for index in range(3))
    if tolerance <= 0:
        return rgb_delta if rgb_delta <= 1 else None
    if rgb_delta > tolerance:
        return None

    rgb = [channel / 255.0 for channel in signature[:3]]
    seed_rgb = [channel / 255.0 for channel in seed_signature[:3]]
    hue, sat, val = colorsys.rgb_to_hsv(*rgb)
    seed_hue, seed_sat, seed_val = colorsys.rgb_to_hsv(*seed_rgb)
    normalized = tolerance / 255.0
    hue_delta = min(abs(hue - seed_hue), 1.0 - abs(hue - seed_hue)) * 360.0
    sat_delta = abs(sat - seed_sat)
    val_delta = abs(val - seed_val)

    if sat > 0.08 and seed_sat > 0.08 and hue_delta > normalized * 60.0:
        return None
    if sat_delta > normalized:
        return None
    if val_delta > normalized:
        return None
    return rgb_delta + hue_delta / 6.0 + sat_delta * 32.0 + val_delta * 64.0


def visual_color_distance(signature, seed_signature):
    if signature is None or seed_signature is None:
        return None
    if len(signature) < 3 or len(seed_signature) < 3:
        return None
    rgb_delta = [abs(signature[index] - seed_signature[index]) for index in range(3)]
    return max(rgb_delta) + sum(rgb_delta) / 6.0


def theme_path_matches_prefix(path, prefix):
    if not path or not prefix:
        return False
    return path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[")


def theme_path_root(path):
    if not path:
        return ""
    root = path.split(".", 1)[0]
    return theme_segment_base_and_index(root)[0]


def area_theme_root(area):
    if area is None:
        return ""
    return AREA_THEME_ROOTS.get(area.type, area.type.lower())


def color_distance_for_path(path, theme_index, seed_signature):
    if seed_signature is None:
        return None
    return visual_color_distance(color_signature(theme_index.get(path)), seed_signature)


def closest_theme_matches(theme_index, seed_signature, prefixes, tolerance=AREA_DIRECT_MATCH_TOLERANCE):
    if seed_signature is None:
        return []
    matches = []
    for path, value in theme_index.items():
        if prefixes and not any(theme_path_matches_prefix(path, prefix) for prefix in prefixes):
            continue
        distance = visual_color_distance(color_signature(value), seed_signature)
        if distance is None or distance > tolerance:
            continue
        matches.append((distance, path))
    matches.sort(key=lambda item: (item[0], item[1]))
    return matches


def layered_closest_theme_matches(theme_index, seed_signature, prefix_layers):
    if seed_signature is None:
        return []
    collected = []
    seen = set()
    for layer, prefixes, tolerance in prefix_layers:
        for distance, path in closest_theme_matches(theme_index, seed_signature, prefixes, tolerance=tolerance):
            if path in seen:
                continue
            seen.add(path)
            collected.append((layer, distance, path))
    return collected


def candidate_with_score(label, path, score, section=""):
    return {
        "label": label,
        "path": path,
        "_score": score,
        "section": section,
    }


def candidate_with_layer(label, path, layer, distance=None, boost=0.0, section=""):
    score = layer * 1000.0 + (distance if distance is not None else 999.0) - boost
    return candidate_with_score(label, path, score, section)


def candidate_group_names(area, region, nearby_regions=None):
    groups = []
    region_types = []
    if region is not None:
        region_types.append(region.type)
    for region_type in nearby_regions or []:
        if region_type not in region_types:
            region_types.append(region_type)

    if "UI" in region_types:
        if area and area.type == "VIEW_3D":
            groups.append("VIEW_3D_PANEL")
        groups.append("PANEL_UI")
    if "TOOLS" in region_types:
        groups.append("PANEL_UI")
    if any(region_type in {"HEADER", "TOOL_HEADER", "NAVIGATION_BAR", "HUD", "MENU"} for region_type in region_types):
        groups.append("MENU_UI")
    if area and area.type == "VIEW_3D":
        is_edit_mode = getattr(bpy.context, "mode", "").startswith("EDIT_")
        if is_edit_mode and (not region_types or "WINDOW" in region_types):
            groups.append("VIEW_3D_EDIT")
    if area is not None and (not region_types or "WINDOW" in region_types):
        groups.append(area.type)
    if _probe_runtime.get("boundary", {}).get("near_any", False):
        groups.append("GLOBAL_BOUNDARY")
    return list(dict.fromkeys(groups))


def dynamic_prefixes_for_probe(area, region, zone, nearby_regions=None):
    prefixes = []
    region_types = []
    if region is not None:
        region_types.append(region.type)
    for region_type in nearby_regions or []:
        if region_type not in region_types:
            region_types.append(region_type)

    root = area_theme_root(area)
    if root and (not region_types or "WINDOW" in region_types):
        prefixes.append(root)

    if not region_types or "WINDOW" in region_types:
        for prefix in COMMON_PREFIXES_BY_AREA.get(getattr(area, "type", ""), ()):
            prefixes.append(prefix)

    if "UI" in region_types:
        prefixes.extend(PANEL_COLOR_PREFIXES)
        if root:
            prefixes.append(f"{root}.space.panelcolors")
    if "TOOLS" in region_types:
        prefixes.extend(TOOL_COLOR_PREFIXES)
    if any(region_type in {"HEADER", "TOOL_HEADER", "NAVIGATION_BAR", "HUD", "MENU"} for region_type in region_types):
        prefixes.extend(HEADER_COLOR_PREFIXES)
        if root:
            prefixes.extend((f"{root}.space.header", f"{root}.space.header_text", f"{root}.space.header_text_hi"))
    if zone in {"TOPBAR", "FALLBACK_TOP_CHROME"}:
        prefixes.extend(("topbar", "user_interface.wcol_menu", "user_interface.wcol_menu_item"))
    if zone in {"VIEW_3D_CONTENT"} and getattr(area, "type", "") == "VIEW_3D":
        prefixes.extend(("view_3d", "common.curves"))
    if _probe_runtime.get("boundary", {}).get("near_any", False):
        prefixes.extend((
            "user_interface.editor_border",
            "user_interface.editor_outline",
            "user_interface.editor_outline_active",
            "user_interface.wcol_regular.outline",
            "user_interface.wcol_tool.outline",
            "user_interface.wcol_menu.outline",
            "user_interface.wcol_list_item.outline",
        ))

    return list(dict.fromkeys(prefixes))


def region_prefixes_for_probe(area, region, zone):
    if region is None:
        return []
    root = area_theme_root(area)
    prefixes = []
    region_type = region.type
    if region_type == "UI":
        prefixes.extend(PANEL_COLOR_PREFIXES)
        if root:
            prefixes.append(f"{root}.space.panelcolors")
    elif region_type == "TOOLS":
        prefixes.extend(TOOL_COLOR_PREFIXES)
    elif region_type in {"HEADER", "TOOL_HEADER", "NAVIGATION_BAR", "HUD", "MENU"}:
        prefixes.extend(HEADER_COLOR_PREFIXES)
        if root:
            prefixes.extend((f"{root}.space.header", f"{root}.space.header_text", f"{root}.space.header_text_hi"))
    elif region_type == "WINDOW":
        if root:
            prefixes.append(root)
        if zone == "VIEW_3D_CONTENT":
            prefixes.extend(("view_3d", "common.curves", "bone_color_sets"))
    return list(dict.fromkeys(prefixes))


def area_prefixes_for_probe(area):
    root = area_theme_root(area)
    prefixes = []
    if root:
        prefixes.append(root)
    return list(dict.fromkeys(prefixes))


def content_prefixes_for_probe(area, region):
    if region is not None and region.type != "WINDOW":
        return []
    return list(COMMON_PREFIXES_BY_AREA.get(getattr(area, "type", ""), ()))


def global_ui_prefixes_for_probe():
    return list(dict.fromkeys((
        "user_interface",
        "regions",
        "topbar",
        "statusbar",
    )))


def region_box_candidates(area, region):
    return (
        (region.x, region.y, region.width, region.height),
        (area.x + region.x, area.y + region.y, region.width, region.height),
    )


def box_distance_to_point(box, x, y):
    left, bottom, width, height = box
    right = left + width
    top = bottom + height
    dx = max(left - x, 0, x - right)
    dy = max(bottom - y, 0, y - top)
    return math.hypot(dx, dy)


def distance_to_region(area, region, mouse_x, mouse_y):
    try:
        return min(box_distance_to_point(box, mouse_x, mouse_y) for box in region_box_candidates(area, region))
    except Exception:
        return 1e9


def nearby_region_types(area, mouse_x, mouse_y, radius=AREA_NEARBY_REGION_RADIUS):
    if area is None:
        return []
    matches = []
    for region in area.regions:
        if region.width <= 1 or region.height <= 1:
            continue
        distance = distance_to_region(area, region, mouse_x, mouse_y)
        if distance <= radius:
            matches.append((distance, region_priority(region), region.type))
    matches.sort()
    result = []
    for _distance, _priority, region_type in matches:
        if region_type not in result:
            result.append(region_type)
    return result


def dynamic_candidate_score(path, theme_index, seed_signature, area, region, zone, prefixes, preferred_index):
    score = 100.0
    root = theme_path_root(path)
    area_root = area_theme_root(area)

    if path in preferred_index:
        score -= 40.0 - min(20.0, preferred_index[path] * 1.25)
    if area_root and root == area_root:
        score -= 22.0
    if root == "user_interface":
        score -= 5.0
    if any(theme_path_matches_prefix(path, prefix) for prefix in prefixes):
        score -= 18.0
    if path.endswith(".outline") or path.endswith(".editor_border") or path.endswith(".editor_outline"):
        if _probe_runtime.get("boundary", {}).get("near_any", False):
            score -= 14.0
        else:
            score += 8.0

    region_type = region.type if region else ""
    if region_type == "WINDOW" and root == "user_interface":
        score += 18.0
    if region_type in {"UI", "TOOLS"} and root == area_root:
        score += 4.0
    if region_type in {"HEADER", "TOOL_HEADER"} and ".space." in path:
        score -= 8.0

    distance = color_distance_for_path(path, theme_index, seed_signature)
    if distance is None:
        return score
    if distance <= AREA_COLOR_MATCH_TOLERANCE:
        score -= 22.0
        score += distance * 0.42
    else:
        score += min(42.0, (distance - AREA_COLOR_MATCH_TOLERANCE) * 0.35)
    return score


def sort_area_candidates(candidates):
    candidates.sort(key=lambda item: (item.get("_score", 999.0), item["path"]))
    sorted_candidates = []
    seen = set()
    for item in candidates:
        path = item["path"]
        if path in seen:
            continue
        seen.add(path)
        sorted_candidates.append({"label": item["label"], "path": path, "section": item.get("section", "")})
    return sorted_candidates


def semantic_label_for_path(path):
    path = canonical_theme_path(path)
    if path in THEME_PATH_LABELS_EN:
        return THEME_PATH_LABELS_EN[path]
    for entries in SEMANTIC_MAP.values():
        for label_text, entry_path in entries:
            entry_path = canonical_theme_path(entry_path)
            if entry_path == path:
                return label_text
    return readable_theme_path_label(path) or path.split(".")[-1]


def get_theme_value(path):
    owner, attr = resolve_theme_path(path)
    if owner is None:
        return None
    try:
        value = getattr(owner, attr)
    except Exception:
        return None
    color = color_to_list(value)
    if color is not None:
        return tuple(round(channel, 6) for channel in color)
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return None


def theme_token():
    root = theme_root()
    if root is None:
        return None
    return (
        getattr(root, "name", "") or "active-theme",
        getattr(root, "filepath", "") or "",
    )


def snapshot_theme_values():
    values = {}
    for path in build_theme_index():
        values[path] = get_theme_value(path)
    for group in build_mode_color_groups():
        for item in group["enums"]:
            values[item["path"]] = get_theme_value(item["path"])
    return values


def restore_theme_values(values):
    global _suspend_history
    _suspend_history = True
    try:
        for path, value in values.items():
            owner, attr = resolve_theme_path(path)
            if owner is None or value is None:
                continue
            try:
                setattr(owner, attr, value)
            except Exception:
                pass
    finally:
        _suspend_history = False
    tag_redraw_all()


def changed_value_count(previous, current):
    if previous is None or current is None:
        return 0
    keys = set(previous.keys()) | set(current.keys())
    return sum(1 for key in keys if previous.get(key) != current.get(key))


def _push_undo_state(state):
    if state is None:
        return
    _theme_history.append(dict(state))
    del _theme_history[:-50]


def _push_redo_state(state):
    if state is None:
        return
    _theme_redo_history.append(dict(state))
    del _theme_redo_history[:-50]


def _clear_history_stacks():
    _theme_history.clear()
    _theme_redo_history.clear()


def _clear_pending_history():
    global _pending_history_before, _pending_history_after, _pending_history_last_change_time, _pending_history_token
    global _pending_history_is_similar_sync
    _pending_history_before = None
    _pending_history_after = None
    _pending_history_last_change_time = 0.0
    _pending_history_token = None
    _pending_history_is_similar_sync = False


def commit_pending_theme_history(force=False):
    global _pending_history_before, _pending_history_after, _pending_history_last_change_time, _pending_history_token
    if _pending_history_before is None or _pending_history_after is None:
        return False

    current_token = theme_token()
    if _pending_history_token != current_token:
        _clear_pending_history()
        return False

    if not force and (time.time() - _pending_history_last_change_time) < _history_commit_delay:
        return False

    changed_count = changed_value_count(_pending_history_before, _pending_history_after)
    if changed_count and (
        _pending_history_is_similar_sync
        or changed_count <= max(24, len(_pending_history_after) // 4)
    ):
        _push_undo_state(_pending_history_before)
        _theme_redo_history.clear()

    _clear_pending_history()
    return True


def reset_theme_history(context=None):
    global _last_theme_state, _last_theme_token
    _clear_history_stacks()
    _clear_pending_history()
    _last_theme_state = snapshot_theme_values()
    _last_theme_token = theme_token()
    if context is not None:
        tag_redraw_all()


def sync_theme_history_to_current_state():
    global _last_theme_state, _last_theme_token
    _clear_pending_history()
    _last_theme_state = snapshot_theme_values()
    _last_theme_token = theme_token()


def restore_theme_state_for_history(values):
    restore_theme_values(values)


def monitor_theme_history():
    global _last_theme_state, _last_theme_token, _history_timer_running
    global _pending_history_before, _pending_history_after, _pending_history_last_change_time, _pending_history_token
    global _pending_history_is_similar_sync
    if not _history_timer_running:
        return None
    if _suspend_history:
        return HISTORY_TIMER_INTERVAL

    commit_pending_theme_history(force=False)

    current_token = theme_token()
    raw_current_state = snapshot_theme_values()
    preview_state_active = state_has_candidate_preview_value(raw_current_state)
    current_state = normalized_candidate_preview_state(raw_current_state)
    if _last_theme_state is None:
        _last_theme_state = current_state
        _last_theme_token = current_token
        _clear_pending_history()
        return HISTORY_TIMER_INTERVAL

    if current_token != _last_theme_token:
        _clear_history_stacks()
        _clear_pending_history()
        _last_theme_state = current_state
        _last_theme_token = current_token
        return HISTORY_TIMER_INTERVAL

    changed_count = changed_value_count(_last_theme_state, current_state)
    if changed_count:
        similar_sync_applied = False
        if not preview_state_active:
            current_state, similar_sync_applied = apply_similar_hsv_offset_from_change(bpy.context, _last_theme_state, current_state)
        changed_count = changed_value_count(_last_theme_state, current_state)
        if changed_count > max(24, len(current_state) // 4) and not similar_sync_applied:
            _clear_history_stacks()
            _clear_pending_history()
        else:
            if _pending_history_before is None:
                _pending_history_before = dict(_last_theme_state)
            _pending_history_after = dict(current_state)
            _pending_history_last_change_time = time.time()
            _pending_history_token = current_token
            _pending_history_is_similar_sync = _pending_history_is_similar_sync or similar_sync_applied
        _last_theme_state = current_state

    commit_pending_theme_history(force=False)
    return HISTORY_TIMER_INTERVAL


def ensure_history_timer():
    global _history_timer_running, _last_theme_state, _last_theme_token
    if _last_theme_state is None:
        _last_theme_state = snapshot_theme_values()
        _last_theme_token = theme_token()
    if not _history_timer_running:
        _history_timer_running = True
        bpy.app.timers.register(monitor_theme_history, first_interval=HISTORY_TIMER_INTERVAL)


def stop_history_timer():
    global _history_timer_running
    _history_timer_running = False


def undo_theme_change():
    global _last_theme_state, _last_theme_token
    restore_candidate_preview()
    commit_pending_theme_history(force=True)
    current_token = theme_token()
    current_state = snapshot_theme_values()
    if current_token != _last_theme_token:
        reset_theme_history()
        return False
    if _last_theme_state is not None and changed_value_count(_last_theme_state, current_state):
        _push_undo_state(_last_theme_state)
        _last_theme_state = current_state
    if not _theme_history:
        return False
    previous = _theme_history.pop()
    _push_redo_state(current_state)
    restore_theme_state_for_history(previous)
    _last_theme_state = snapshot_theme_values()
    return True


def redo_theme_change():
    global _last_theme_state, _last_theme_token
    restore_candidate_preview()
    commit_pending_theme_history(force=True)
    current_token = theme_token()
    current_state = snapshot_theme_values()
    if current_token != _last_theme_token:
        reset_theme_history()
        return False
    if not _theme_redo_history:
        return False
    next_state = _theme_redo_history.pop()
    _push_undo_state(current_state)
    restore_theme_state_for_history(next_state)
    _last_theme_state = snapshot_theme_values()
    return True


def candidate_color_paths_from_window_manager(wm):
    paths = []
    for item in getattr(wm, "theme_probe_candidates", []):
        path = getattr(item, "path", "")
        if path and path not in paths and is_color_theme_path(path):
            paths.append(path)
    return paths


def candidate_path_locked(path):
    return bool(path and path in _locked_candidate_paths)


def candidate_path_lock_icon(path):
    return "LOCKED" if candidate_path_locked(path) else "UNLOCKED"


def unlocked_candidate_color_paths_from_window_manager(wm):
    return [
        path for path in candidate_color_paths_from_window_manager(wm)
        if not candidate_path_locked(path)
    ]


def similar_sync_enabled(context):
    if context is None:
        return True
    wm = context.window_manager
    return bool(getattr(wm, "theme_probe_sync_similar", True))


def auto_disable_similar_sync_for_preview(context):
    global _candidate_preview_auto_disabled_sync
    if context is None:
        return
    wm = context.window_manager
    if (
        getattr(wm, "theme_probe_mode", "AREA") == "SIMILAR"
        and getattr(wm, "theme_probe_sync_similar", True)
    ):
        wm.theme_probe_sync_similar = False
        _candidate_preview_auto_disabled_sync = True


def restore_auto_disabled_similar_sync(context):
    global _candidate_preview_auto_disabled_sync
    if not _candidate_preview_auto_disabled_sync:
        return False
    if context is not None:
        context.window_manager.theme_probe_sync_similar = True
    _candidate_preview_auto_disabled_sync = False
    return True


def hsv_offset_color(color, hsv_delta):
    if color is None or len(color) < 3:
        return None
    hue, sat, val = colorsys.rgb_to_hsv(*color[:3])
    hue, sat, val = clamp_hsv_triplet(
        hue + hsv_delta[0],
        sat + hsv_delta[1],
        val + hsv_delta[2],
    )
    red, green, blue = colorsys.hsv_to_rgb(hue, sat, val)
    result = [clamp(red), clamp(green), clamp(blue)]
    if len(color) >= 4:
        result.append(clamp(color[3]))
    return tuple(result)


def value_offset_color(color, value_delta):
    if color is None or len(color) < 3:
        return None
    hue, sat, val = colorsys.rgb_to_hsv(*color[:3])
    red, green, blue = colorsys.hsv_to_rgb(hue, sat, clamp(val + value_delta))
    result = [clamp(red), clamp(green), clamp(blue)]
    if len(color) >= 4:
        result.append(clamp(color[3]))
    return tuple(result)


def preview_pulse_color(color, phase):
    if color is None or len(color) < 3:
        return None
    hue, sat, val = colorsys.rgb_to_hsv(*color[:3])
    span = CANDIDATE_PREVIEW_VALUE_AMPLITUDE
    half_span = span * 0.5
    lower = val - half_span
    upper = val + half_span
    if upper > 1.0:
        upper = 1.0
        lower = max(0.0, upper - span)
    elif lower < 0.0:
        lower = 0.0
        upper = min(1.0, lower + span)
    center = (lower + upper) * 0.5
    amplitude = (upper - lower) * 0.5
    pulse_value = center + math.cos(phase * math.tau) * amplitude
    red, green, blue = colorsys.hsv_to_rgb(hue, sat, clamp(pulse_value))
    result = [clamp(red), clamp(green), clamp(blue)]
    if len(color) >= 4:
        result.append(clamp(color[3]))
    return tuple(result)


def colors_close(first, second, epsilon=0.0005):
    if first is None or second is None:
        return False
    if len(first) != len(second):
        return False
    return all(abs(first[index] - second[index]) <= epsilon for index in range(len(first)))


def active_candidate_color_path(context):
    wm = context.window_manager
    items = getattr(wm, "theme_probe_candidates", None)
    if not items:
        return ""
    index = getattr(wm, "theme_probe_candidate_preview_index", -1)
    if index < 0 or index >= len(items):
        return ""
    path = getattr(items[index], "path", "")
    if candidate_path_locked(path):
        return ""
    return path if is_color_theme_path(path) else ""


def restore_candidate_preview():
    global _candidate_preview_path, _candidate_preview_original, _candidate_preview_last_written, _candidate_preview_start_time
    global _candidate_preview_last_draw_time
    if _candidate_preview_path and _candidate_preview_original is not None:
        current = color_value_for_path(_candidate_preview_path)
        if _candidate_preview_last_written is None or colors_close(current, _candidate_preview_last_written):
            set_color_value_for_path_without_history(_candidate_preview_path, _candidate_preview_original)
    _candidate_preview_path = ""
    _candidate_preview_original = None
    _candidate_preview_last_written = None
    _candidate_preview_start_time = 0.0
    _candidate_preview_last_draw_time = 0.0


def stop_candidate_preview_from_mouse(context):
    restore_candidate_preview()
    if _candidate_preview_auto_disabled_sync:
        sync_theme_history_to_current_state()
    restored_sync = restore_auto_disabled_similar_sync(context)
    if context is not None:
        context.window_manager.theme_probe_candidate_preview_index = -1
    return restored_sync


def set_color_value_for_path_without_history(path, color):
    global _suspend_history
    was_suspended = _suspend_history
    _suspend_history = True
    try:
        return set_color_value_for_path(path, color)
    finally:
        _suspend_history = was_suspended


def normalized_candidate_preview_state(state):
    if (
        state is None
        or not _candidate_preview_path
        or _candidate_preview_original is None
        or _candidate_preview_last_written is None
    ):
        return state
    current_value = state.get(_candidate_preview_path)
    if colors_close(current_value, _candidate_preview_last_written):
        normalized = dict(state)
        normalized[_candidate_preview_path] = tuple(round(channel, 6) for channel in _candidate_preview_original)
        return normalized
    return state


def state_has_candidate_preview_value(state):
    if (
        state is None
        or not _candidate_preview_path
    ):
        return False
    current_value = state.get(_candidate_preview_path)
    if _candidate_preview_last_written is not None and colors_close(current_value, _candidate_preview_last_written):
        return True
    return False


def schedule_candidate_preview(context):
    global _candidate_preview_path, _candidate_preview_original, _candidate_preview_start_time
    global _candidate_preview_last_draw_time, _candidate_preview_timer_running, _candidate_preview_last_written
    path = active_candidate_color_path(context)
    now = time.time()
    _candidate_preview_last_draw_time = now
    if not path:
        restore_candidate_preview()
        return
    if path != _candidate_preview_path:
        restore_candidate_preview()
        _candidate_preview_path = path
        _candidate_preview_original = color_value_for_path(path)
        _candidate_preview_last_written = _candidate_preview_original
        _candidate_preview_start_time = now
        _candidate_preview_last_draw_time = now
    if not _candidate_preview_timer_running:
        _candidate_preview_timer_running = True
        bpy.app.timers.register(candidate_preview_timer, first_interval=CANDIDATE_PREVIEW_INTERVAL)


def candidate_preview_timer():
    global _candidate_preview_timer_running, _candidate_preview_last_written
    if not _candidate_preview_path or _candidate_preview_original is None:
        _candidate_preview_timer_running = False
        return None

    now = time.time()
    if active_candidate_color_path(bpy.context) != _candidate_preview_path:
        restore_candidate_preview()
        _candidate_preview_timer_running = False
        tag_redraw_all()
        return None

    elapsed = now - _candidate_preview_start_time
    if elapsed < CANDIDATE_PREVIEW_DELAY:
        return CANDIDATE_PREVIEW_INTERVAL

    current_color = color_value_for_path(_candidate_preview_path)
    if _candidate_preview_last_written is not None and not colors_close(current_color, _candidate_preview_last_written):
        restore_candidate_preview()
        _candidate_preview_timer_running = False
        tag_redraw_all()
        return None

    phase = (elapsed - CANDIDATE_PREVIEW_DELAY) / CANDIDATE_PREVIEW_CYCLE
    preview_color = preview_pulse_color(_candidate_preview_original, phase)
    if preview_color is not None:
        set_color_value_for_path_without_history(_candidate_preview_path, preview_color)
        _candidate_preview_last_written = color_value_for_path(_candidate_preview_path)
        tag_redraw_all()
    return CANDIDATE_PREVIEW_INTERVAL


def update_candidate_index(self, context):
    if context is not None:
        wm = context.window_manager
        preview_index = getattr(wm, "theme_probe_candidate_preview_index", -1)
        active_index = getattr(wm, "theme_probe_candidate_index", -1)
        items = getattr(wm, "theme_probe_candidates", None)
        if preview_index >= 0:
            if items and 0 <= active_index < len(items):
                if preview_index != active_index:
                    restore_candidate_preview()
                    wm.theme_probe_candidate_preview_index = active_index
            else:
                restore_candidate_preview()
                wm.theme_probe_candidate_preview_index = -1
        schedule_candidate_preview(context)


def apply_similar_hsv_offset_from_change(context, previous_state, current_state):
    global _syncing_similar_colors
    if _syncing_similar_colors:
        return current_state, False
    if context is None:
        return current_state, False

    wm = context.window_manager
    if getattr(wm, "theme_probe_mode", "AREA") != "SIMILAR":
        return current_state, False
    if not similar_sync_enabled(context):
        return current_state, False

    candidate_paths = unlocked_candidate_color_paths_from_window_manager(wm)
    if len(candidate_paths) < 2:
        return current_state, False

    changed_paths = [
        path for path in candidate_paths
        if previous_state.get(path) != current_state.get(path)
        and previous_state.get(path) is not None
        and current_state.get(path) is not None
    ]
    if len(changed_paths) != 1:
        return current_state, False

    source_path = changed_paths[0]
    source_before = previous_state.get(source_path)
    source_after = current_state.get(source_path)
    if len(source_before) < 3 or len(source_after) < 3:
        return current_state, False

    before_hsv = colorsys.rgb_to_hsv(*source_before[:3])
    after_hsv = colorsys.rgb_to_hsv(*source_after[:3])
    hsv_delta = tuple(after_hsv[index] - before_hsv[index] for index in range(3))
    if not any(abs(delta) > 1e-9 for delta in hsv_delta):
        return current_state, False

    updated_state = dict(current_state)
    _syncing_similar_colors = True
    try:
        for path in candidate_paths:
            if path == source_path:
                continue
            original_color = previous_state.get(path)
            if original_color is None:
                continue
            shifted_color = hsv_offset_color(original_color, hsv_delta)
            if shifted_color is None:
                continue
            if set_color_value_for_path(path, shifted_color):
                updated_state[path] = get_theme_value(path)
    finally:
        _syncing_similar_colors = False

    similar_sync_applied = updated_state != current_state
    if similar_sync_applied:
        tag_redraw_all()
    return updated_state, similar_sync_applied


def ensure_snapshot():
    global _theme_snapshot
    if _theme_snapshot is not None:
        return
    refresh_snapshot()


def refresh_snapshot():
    global _theme_snapshot
    snapshot = {}
    for path, value in build_theme_index().items():
        color = color_to_list(value)
        if color is not None:
            snapshot[path] = color
    _theme_snapshot = snapshot


def restore_snapshot():
    if not _theme_snapshot:
        return False
    for path, color in _theme_snapshot.items():
        owner, attr = resolve_theme_path(path)
        if owner is None:
            continue
        try:
            setattr(owner, attr, color)
        except Exception:
            pass
    tag_redraw_all()
    return True


class ThemeSnapshotManager:
    @staticmethod
    def ensure_snapshot():
        ensure_snapshot()

    @staticmethod
    def restore():
        return restore_snapshot()


def tag_redraw_all():
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            area.tag_redraw()


def point_inside_region(area, region, x, y):
    boxes = (
        (region.x, region.y, region.width, region.height),
        (area.x + region.x, area.y + region.y, region.width, region.height),
    )
    return any(rx <= x <= rx + width and ry <= y <= ry + height for rx, ry, width, height in boxes)


def region_priority(region):
    priorities = {
        "HEADER": 0,
        "TOOL_HEADER": 1,
        "TOOLS": 2,
        "UI": 3,
        "NAVIGATION_BAR": 4,
        "HUD": 5,
        "WINDOW": 20,
    }
    return priorities.get(region.type, 10)


def find_area_region(screen, mouse_x, mouse_y):
    for area in screen.areas:
        if area.x <= mouse_x <= area.x + area.width and area.y <= mouse_y <= area.y + area.height:
            matching_regions = []
            for region in area.regions:
                if region.width > 1 and region.height > 1 and point_inside_region(area, region, mouse_x, mouse_y):
                    matching_regions.append(region)
            if matching_regions:
                matching_regions.sort(key=region_priority)
                return area, matching_regions[0]
            return area, None
    return None, None


def screen_top_area_type(screen, mouse_y):
    if screen is None:
        return ""
    try:
        top_area = max(screen.areas, key=lambda item: item.y + item.height)
    except ValueError:
        return ""
    if mouse_y >= top_area.y and top_area.type in {"TOPBAR", "STATUSBAR"}:
        return top_area.type
    return ""


def classify_probe_zone(screen, area, region, mouse_x, mouse_y):
    if area is None:
        return "NONE"
    if area.type == "TOPBAR":
        return "TOPBAR"
    top_type = screen_top_area_type(screen, mouse_y)
    if top_type == "TOPBAR":
        return "TOPBAR"
    if area.type == "VIEW_3D":
        region_type = region.type if region else ""
        if region_type == "HEADER":
            return "VIEW_3D_HEADER"
        if region_type == "TOOL_HEADER":
            return "VIEW_3D_TOOL_HEADER"
        if region_type == "TOOLS":
            return "VIEW_3D_TOOLBAR"
        if region_type == "UI":
            return "VIEW_3D_SIDEBAR"
        if region_type == "WINDOW":
            return "VIEW_3D_CONTENT"
    return f"{area.type}_{region.type}" if region else area.type


def display_zone_label(zone):
    labels = {
        "TOPBAR": "Top Menu / Workspace Bar",
        "VIEW_3D_HEADER": "3D View Header",
        "VIEW_3D_TOOL_HEADER": "3D View Tool Header",
        "VIEW_3D_TOOLBAR": "3D View Left Toolbar",
        "VIEW_3D_SIDEBAR": "3D View Right Sidebar",
        "VIEW_3D_CONTENT": "3D View Content",
        "FALLBACK_TOP_CHROME": "Top UI Area",
        "FALLBACK_BOTTOM_STATUS": "Bottom Status Bar",
        "FALLBACK_AREA_SEPARATOR": "Area Separator / Boundary",
        "FALLBACK_SCREEN": "Screenshot Lookup Area",
    }
    return tr(labels.get(zone, zone))


def screen_area_bounds(screen):
    areas = list(getattr(screen, "areas", []))
    if not areas:
        return None
    return {
        "left": min(area.x for area in areas),
        "right": max(area.x + area.width for area in areas),
        "bottom": min(area.y for area in areas),
        "top": max(area.y + area.height for area in areas),
    }


def distance_to_area(area, mouse_x, mouse_y):
    left = area.x
    right = area.x + area.width
    bottom = area.y
    top = area.y + area.height
    dx = max(left - mouse_x, 0, mouse_x - right)
    dy = max(bottom - mouse_y, 0, mouse_y - top)
    return dx + dy


def nearest_screen_area(screen, mouse_x, mouse_y):
    areas = list(getattr(screen, "areas", []))
    if not areas:
        return None
    return min(areas, key=lambda area: distance_to_area(area, mouse_x, mouse_y))


def boundary_flags_from_point(area, mouse_x, mouse_y):
    if area is None:
        return {}
    distances = {
        "left": abs(mouse_x - area.x),
        "right": abs(mouse_x - (area.x + area.width)),
        "bottom": abs(mouse_y - area.y),
        "top": abs(mouse_y - (area.y + area.height)),
    }
    nearest = min(distances, key=distances.get)
    return {
        "left": nearest == "left",
        "right": nearest == "right",
        "bottom": nearest == "bottom",
        "top": nearest == "top",
        "near_any": True,
    }


def classify_fallback_zone(screen, mouse_x, mouse_y, nearest_area):
    bounds = screen_area_bounds(screen)
    if bounds is None:
        return "FALLBACK_SCREEN"
    if mouse_y >= bounds["top"]:
        return "FALLBACK_TOP_CHROME"
    if mouse_y <= bounds["bottom"]:
        return "FALLBACK_BOTTOM_STATUS"
    if nearest_area is not None:
        if nearest_area.type == "TOPBAR":
            return "FALLBACK_TOP_CHROME"
        if nearest_area.type == "STATUSBAR":
            return "FALLBACK_BOTTOM_STATUS"
    return "FALLBACK_AREA_SEPARATOR"


def fallback_preferred_groups(zone, nearest_area):
    groups = []
    if zone == "FALLBACK_TOP_CHROME":
        groups.extend(["MENU_UI", "GLOBAL_BOUNDARY"])
    elif zone == "FALLBACK_BOTTOM_STATUS":
        groups.extend(["MENU_UI", "GLOBAL_BOUNDARY"])
    elif zone == "FALLBACK_AREA_SEPARATOR":
        groups.extend(["GLOBAL_BOUNDARY", "MENU_UI"])
    if nearest_area is not None:
        groups.append(nearest_area.type)
    return groups


def semantic_paths_for_groups(groups):
    paths = []
    theme_index = build_theme_index()
    for group in groups:
        for _label, path in SEMANTIC_MAP.get(group, []):
            path = canonical_theme_path(path, theme_index)
            if path not in paths:
                paths.append(path)
    return paths


def collect_visual_color_candidates(sample_color, zone, nearest_area=None):
    seed_signature = signature_from_color(sample_color)
    if seed_signature is None:
        return []
    preferred_paths = semantic_paths_for_groups(fallback_preferred_groups(zone, nearest_area))
    preferred_index = {path: index for index, path in enumerate(preferred_paths)}
    preferred_prefixes = [area_theme_root(nearest_area)] if nearest_area is not None else []
    preferred_prefixes.extend(fallback_preferred_groups(zone, nearest_area))
    matches = []
    for path, value in build_theme_index().items():
        signature = color_signature(value)
        distance = visual_color_distance(signature, seed_signature)
        if distance is None or distance > FALLBACK_MATCH_TOLERANCE:
            continue
        semantic_bonus = 0.0
        if path in preferred_index:
            semantic_bonus = 18.0 - min(12.0, preferred_index[path] * 1.5)
        if any(theme_path_matches_prefix(path, prefix) for prefix in preferred_prefixes if prefix):
            semantic_bonus += 10.0
        matches.append({
            "label": semantic_label_for_path(path),
            "path": path,
            "distance": max(0.0, distance - semantic_bonus),
        })
    matches.sort(key=lambda item: (item["distance"], item["path"]))
    return matches


def boundary_flags(area, mouse_x, mouse_y):
    if area is None:
        return {}
    return {
        "left": abs(mouse_x - area.x) <= BOUNDARY_THRESHOLD,
        "right": abs(mouse_x - (area.x + area.width)) <= BOUNDARY_THRESHOLD,
        "bottom": abs(mouse_y - area.y) <= BOUNDARY_THRESHOLD,
        "top": abs(mouse_y - (area.y + area.height)) <= BOUNDARY_THRESHOLD,
        "near_any": (
            abs(mouse_x - area.x) <= BOUNDARY_THRESHOLD
            or abs(mouse_x - (area.x + area.width)) <= BOUNDARY_THRESHOLD
            or abs(mouse_y - area.y) <= BOUNDARY_THRESHOLD
            or abs(mouse_y - (area.y + area.height)) <= BOUNDARY_THRESHOLD
        ),
    }


def collect_candidates(area, region, sample_color=None, mouse_x=None, mouse_y=None, nearby_regions=None):
    theme_index = build_theme_index()
    zone = _probe_runtime.get("zone", "")
    groups = candidate_group_names(area, region, nearby_regions)
    region_prefixes = region_prefixes_for_probe(area, region, zone)
    area_prefixes = area_prefixes_for_probe(area)
    content_prefixes = content_prefixes_for_probe(area, region)
    global_prefixes = global_ui_prefixes_for_probe()
    prefixes = dynamic_prefixes_for_probe(area, region, zone, nearby_regions)
    preferred_paths = semantic_paths_for_groups(groups)
    preferred_index = {path: index for index, path in enumerate(preferred_paths)}
    seed_signature = signature_from_color(sample_color)
    candidates = []
    seen = set()

    def append_candidate(label_text, path, layer, distance=None, boost=0.0, section=""):
        if path not in theme_index or path in seen:
            return False
        seen.add(path)
        candidates.append(candidate_with_layer(label_text, path, layer, distance, boost, section))
        return True

    for path, label_text in learned_candidate_paths():
        append_candidate(label_text or semantic_label_for_path(path), path, -1, 0.0, 0.0, "Learned")

    direct_prefixes = region_prefixes or area_prefixes + content_prefixes
    direct_layers = [
        (0, direct_prefixes, AREA_DIRECT_MATCH_TOLERANCE),
        (0.12, area_prefixes + content_prefixes, AREA_DIRECT_MATCH_TOLERANCE + 8),
        (0.24, global_prefixes, AREA_DIRECT_MATCH_TOLERANCE + 10),
        (0.36, [], max(8, AREA_DIRECT_MATCH_TOLERANCE - 6)),
    ]
    for layer, distance, path in layered_closest_theme_matches(theme_index, seed_signature, direct_layers):
        append_candidate(semantic_label_for_path(path), path, layer, distance, 20.0, "Pointer Color")

    for group in groups:
        for label_text, path in SEMANTIC_MAP.get(group, []):
            path = canonical_theme_path(path, theme_index)
            distance = color_distance_for_path(path, theme_index, seed_signature)
            layer = 1
            if region_prefixes and any(theme_path_matches_prefix(path, prefix) for prefix in region_prefixes):
                layer = 1
            elif content_prefixes and any(theme_path_matches_prefix(path, prefix) for prefix in content_prefixes):
                layer = 2
            elif area_prefixes and any(theme_path_matches_prefix(path, prefix) for prefix in area_prefixes):
                layer = 2
            else:
                layer = 3
            boost = max(0.0, 24.0 - min(24.0, preferred_index.get(path, 0) * 2.0))
            section = "Current Region" if layer == 1 else ("Current Area" if layer == 2 else "UI Fallback")
            append_candidate(label_text, path, layer, distance, boost, section)

    for path in theme_index.keys():
        if path in seen:
            continue
        if not any(theme_path_matches_prefix(path, prefix) for prefix in prefixes):
            continue
        distance = color_distance_for_path(path, theme_index, seed_signature)
        layer = 4
        if region_prefixes and any(theme_path_matches_prefix(path, prefix) for prefix in region_prefixes):
            layer = 1
        elif content_prefixes and any(theme_path_matches_prefix(path, prefix) for prefix in content_prefixes):
            layer = 2
        elif area_prefixes and any(theme_path_matches_prefix(path, prefix) for prefix in area_prefixes):
            layer = 2
        elif global_prefixes and any(theme_path_matches_prefix(path, prefix) for prefix in global_prefixes):
            layer = 3
        section = "Current Region" if layer == 1 else ("Current Area" if layer == 2 else ("UI Fallback" if layer == 3 else "Fallback"))
        append_candidate(semantic_label_for_path(path), path, layer, distance, section=section)

    if not candidates:
        area_root = area_theme_root(area)
        fallback_paths = [
            path for path in theme_index.keys()
            if area_root and theme_path_matches_prefix(path, area_root)
        ]
        if not fallback_paths:
            fallback_paths = list(sorted(theme_index.keys()))
        for path in fallback_paths:
            candidates.append(candidate_with_score(semantic_label_for_path(path), path, 100.0, "Fallback"))

    return sort_area_candidates(candidates)


def collect_similar_candidates(seed_signature, tolerance):
    theme_index = build_theme_index()
    if seed_signature is None:
        return []

    matches = []
    for path, value in theme_index.items():
        signature = color_signature(value)
        if signature is None:
            continue
        distance = color_match_distance(signature, seed_signature, tolerance)
        if distance is not None:
            matches.append({
                "label": semantic_label_for_path(path),
                "path": path,
                "distance": distance,
            })
    matches.sort(key=lambda item: (item["distance"], item["path"]))
    return matches


def is_color_theme_path(path):
    owner, attr = resolve_theme_path(path)
    if owner is None:
        return False
    try:
        return color_to_list(getattr(owner, attr)) is not None
    except Exception:
        return False


def active_probe_candidates(context):
    wm = context.window_manager
    candidates = _probe_runtime.get("candidates", [])
    if getattr(wm, "theme_probe_mode", "AREA") == "SIMILAR":
        tolerance = getattr(wm, "theme_probe_tolerance", SIMILAR_TOLERANCE_DEFAULT)
        return collect_similar_candidates(_similar_seed_signature, tolerance)
    return candidates


def update_similar_seed_from_candidates(candidates):
    global _similar_seed_candidates, _similar_seed_signature, _similar_seed_path
    _similar_seed_candidates = list(candidates)
    theme_index = build_theme_index()
    for item in _similar_seed_candidates:
        signature = color_signature(theme_index.get(item["path"]))
        if signature is not None:
            _similar_seed_signature = signature
            _similar_seed_path = item["path"]
            return
    _similar_seed_signature = None
    _similar_seed_path = ""


def update_similar_seed_from_sample(context):
    global _similar_seed_candidates, _similar_seed_signature, _similar_seed_path
    wm = context.window_manager
    signature = signature_from_color(getattr(wm, "theme_probe_sample_color", (0.0, 0.0, 0.0, 1.0)))
    _similar_seed_candidates = []
    _similar_seed_signature = signature
    _similar_seed_path = "window_manager.theme_probe_sample_color"
    tag_redraw_all()


def set_sample_color(context, color, refresh_list=True):
    if color is None:
        return False
    wm = context.window_manager
    wm.theme_probe_sample_color = tuple(clamp(channel) for channel in color[:4])
    if refresh_list:
        update_similar_seed_from_sample(context)
        populate_candidate_collection(context)
        tag_redraw_all()
    return True


def schedule_sample_refresh(context):
    global _sample_refresh_pending, _sample_refresh_time, _sample_refresh_timer_running
    _sample_refresh_pending = True
    _sample_refresh_time = time.time()
    if not _sample_refresh_timer_running:
        _sample_refresh_timer_running = True
        bpy.app.timers.register(sample_refresh_timer, first_interval=0.15)


def sample_refresh_timer():
    global _sample_refresh_pending, _sample_refresh_timer_running
    if not _sample_refresh_pending:
        _sample_refresh_timer_running = False
        return None
    if time.time() - _sample_refresh_time < 0.35:
        return 0.15
    _sample_refresh_pending = False
    context = bpy.context
    if getattr(context.window_manager, "theme_probe_mode", "AREA") == "SIMILAR":
        populate_candidate_collection(context)
        tag_redraw_all()
    _sample_refresh_timer_running = False
    return None


def probe_at_position(context, mouse_x, mouse_y):
    area, region = find_area_region(context.screen, mouse_x, mouse_y)
    sample_color = None
    if getattr(context.window_manager, "theme_probe_mode", "AREA") == "SIMILAR":
        sample_color = sample_screen_color(context, mouse_x, mouse_y)
    else:
        sample_color = sample_screen_color(
            context,
            mouse_x,
            mouse_y,
            radius=AREA_SAMPLE_RADIUS,
            center_weight=1000.0,
            exact_pointer=True,
        )
    if area is None:
        nearest_area = nearest_screen_area(context.screen, mouse_x, mouse_y)
        zone = classify_fallback_zone(context.screen, mouse_x, mouse_y, nearest_area)
        candidates = collect_visual_color_candidates(sample_color, zone, nearest_area)
        if not candidates:
            return False
        _probe_runtime.clear()
        _probe_runtime["area_type"] = "SCREEN"
        _probe_runtime["region_type"] = "VISUAL"
        _probe_runtime["zone"] = zone
        _probe_runtime["boundary"] = boundary_flags_from_point(nearest_area, mouse_x, mouse_y)
        _probe_runtime["candidates"] = candidates
        _probe_runtime["sample_color"] = sample_color
        return True
    _probe_runtime.clear()
    _probe_runtime["area_type"] = area.type
    _probe_runtime["region_type"] = region.type if region else ""
    _probe_runtime["zone"] = classify_probe_zone(context.screen, area, region, mouse_x, mouse_y)
    _probe_runtime["boundary"] = boundary_flags(area, mouse_x, mouse_y)
    nearby_regions = nearby_region_types(area, mouse_x, mouse_y)
    _probe_runtime["nearby_regions"] = nearby_regions
    _probe_runtime["sample_color"] = sample_color
    _probe_runtime["candidates"] = collect_candidates(
        area,
        region,
        sample_color=sample_color,
        mouse_x=mouse_x,
        mouse_y=mouse_y,
        nearby_regions=nearby_regions,
    )
    return True


def populate_candidate_collection(context, candidates=None):
    wm = context.window_manager
    collection = getattr(wm, "theme_probe_candidates", None)
    if collection is None:
        return
    if candidates is None:
        candidates = active_probe_candidates(context)
    collection.clear()
    candidate_paths = {item["path"] for item in candidates}
    group_candidate_paths = set() if getattr(wm, "theme_probe_mode", "AREA") == "SIMILAR" else candidate_paths
    label_by_path = {item["path"]: item["label"] for item in candidates}
    section_by_path = {item["path"]: item.get("section", "") for item in candidates}
    grouped_paths = set()
    number = 1
    for group in build_mode_color_groups():
        group_color_paths = {item["path"] for item in group["colors"]}
        matched_color_paths = group_candidate_paths.intersection(group_color_paths)
        if not matched_color_paths:
            continue
        group_items = []
        if getattr(wm, "theme_probe_mode", "AREA") != "SIMILAR":
            group_items.extend(group["enums"])
        group_items.extend(item for item in group["colors"] if item["path"] in matched_color_paths)
        for item in group_items:
            if resolve_theme_path(item["path"])[0] is None:
                continue
            entry = collection.add()
            label_text = label_by_path.get(item["path"]) or ("Background Type" if item["path"].endswith(".background_type") else item["label"])
            label_text = english_theme_label(label_text, item["path"])
            entry.name = label_text
            entry.label = localized_theme_label(label_text, item["path"])
            entry.path = item["path"]
            entry.section = tr(section_by_path.get(item["path"], ""))
            entry.number = number
            number += 1
        grouped_paths.update(matched_color_paths)

    for item in candidates:
        if item["path"] in grouped_paths:
            continue
        if getattr(wm, "theme_probe_mode", "AREA") == "SIMILAR" and not is_color_theme_path(item["path"]):
            continue
        entry = collection.add()
        label_text = english_theme_label(item["label"], item["path"])
        entry.name = label_text
        entry.label = localized_theme_label(label_text, item["path"])
        entry.path = item["path"]
        entry.section = tr(item.get("section", ""))
        entry.number = number
        number += 1
    restore_candidate_preview()
    wm.theme_probe_candidate_index = 0 if len(collection) else -1
    wm.theme_probe_candidate_preview_index = -1


def draw_theme_color_row(layout, label_text, theme_path):
    owner, attr = resolve_theme_path(theme_path)
    if owner is None:
        return False
    row = layout.row(align=True)
    split = row.split(factor=0.58, align=True)
    split.label(text=label_text)
    split.prop(owner, attr, text="")
    return True


def current_candidate_color_paths(context):
    paths = []
    for item in getattr(context.window_manager, "theme_probe_candidates", []):
        if is_color_theme_path(item.path) and item.path not in paths:
            paths.append(item.path)
    return paths


def color_value_for_path(path):
    owner, attr = resolve_theme_path(path)
    if owner is None:
        return None
    try:
        value = getattr(owner, attr)
    except Exception:
        return None
    color = color_to_list(value)
    if color is None or len(color) < 3:
        return None
    if len(color) == 3:
        color.append(1.0)
    return tuple(clamp(channel) for channel in color[:4])


def set_color_value_for_path(path, color):
    owner, attr = resolve_theme_path(path)
    if owner is None:
        return False
    try:
        current = getattr(owner, attr)
        length = len(current)
        setattr(owner, attr, tuple(color[:length]))
        return True
    except Exception:
        return False


class ThemeCandidateResolver:
    @staticmethod
    def resolve(area, region):
        return collect_candidates(area, region)


def prepare_candidate_collection(context):
    populate_candidate_collection(context)


def update_probe_list_settings(self, context):
    if context is not None:
        prepare_candidate_collection(context)
        tag_redraw_all()


def update_sample_color(self, context):
    if context is not None and getattr(context.window_manager, "theme_probe_mode", "AREA") == "SIMILAR":
        update_similar_seed_from_sample(context)
        schedule_sample_refresh(context)


def default_theme_preset_dir():
    return bpy.utils.user_resource("SCRIPTS", path=os.path.join("presets", "interface_theme"), create=True)


def learning_store_path():
    folder = bpy.utils.user_resource("CONFIG", path="theme_dictionary", create=True)
    return os.path.join(folder, "probe_learning.json")


def load_learning_cache():
    global _learning_cache
    if _learning_cache is not None:
        return _learning_cache
    path = learning_store_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            _learning_cache = data
        else:
            _learning_cache = []
    except Exception:
        _learning_cache = []
    return _learning_cache


def save_learning_cache():
    if _learning_cache is None:
        return
    path = learning_store_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(_learning_cache[-LEARNING_STORE_LIMIT:], handle, ensure_ascii=False, indent=2)
    except Exception:
        pass


def current_learning_key():
    return {
        "area": _probe_runtime.get("area_type", ""),
        "region": _probe_runtime.get("region_type", ""),
        "zone": _probe_runtime.get("zone", ""),
        "signature": list(signature_from_color(_probe_runtime.get("sample_color")) or ()),
    }


def learning_context_score(record, key):
    if not record or not key:
        return None
    score = 0.0
    if record.get("area") == key.get("area"):
        score += 18.0
    else:
        return None
    if record.get("region") == key.get("region"):
        score += 14.0
    if record.get("zone") == key.get("zone"):
        score += 8.0
    distance = visual_color_distance(tuple(record.get("signature", ())), tuple(key.get("signature", ())))
    if distance is not None:
        if distance > LEARNING_MATCH_TOLERANCE:
            return None
        score += max(0.0, LEARNING_MATCH_TOLERANCE - distance)
    return score


def learned_candidate_paths():
    key = current_learning_key()
    matches = []
    for index, record in enumerate(load_learning_cache()):
        path = record.get("path", "")
        if not path:
            continue
        score = learning_context_score(record, key)
        if score is None:
            continue
        matches.append((score, record.get("last_used", 0.0), index, path, record.get("label", "")))
    matches.sort(key=lambda item: (-item[0], -item[1], item[2]))
    result = []
    seen = set()
    for _score, _last_used, _index, path, label in matches:
        canonical_path = canonical_theme_path(path)
        if canonical_path in seen:
            continue
        seen.add(canonical_path)
        result.append((canonical_path, label))
    return result


def remember_candidate_choice(context, path, label):
    if not path:
        return
    key = current_learning_key()
    signature = key.get("signature", [])
    if not signature:
        return
    cache = load_learning_cache()
    canonical_path = canonical_theme_path(path)
    now = time.time()
    existing = None
    for record in cache:
        if (
            record.get("path") == canonical_path
            and record.get("area") == key.get("area")
            and record.get("region") == key.get("region")
            and record.get("zone") == key.get("zone")
        ):
            existing = record
            break
    if existing is None:
        existing = {}
        cache.append(existing)
    existing.update({
        "path": canonical_path,
        "label": label or semantic_label_for_path(canonical_path),
        "area": key.get("area", ""),
        "region": key.get("region", ""),
        "zone": key.get("zone", ""),
        "signature": signature,
        "last_used": now,
        "count": int(existing.get("count", 0)) + 1,
    })
    del cache[:-LEARNING_STORE_LIMIT]
    save_learning_cache()


def current_theme_filepath():
    root = theme_root()
    if root is None:
        return ""
    return getattr(root, "filepath", "") or ""


def open_theme_preset_folder():
    folder = default_theme_preset_dir()
    os.makedirs(folder, exist_ok=True)
    bpy.ops.wm.path_open(filepath=folder)
    return folder


def sync_keymaps():
    while addon_keymaps:
        km, kmi = addon_keymaps.pop()
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return
    km = kc.keymaps.new(name="Window", space_type="EMPTY")
    kmi = km.keymap_items.new(
        THEMEPROBE_OT_probe.bl_idname,
        "C",
        "PRESS",
        alt=True,
        ctrl=False,
        shift=False,
    )
    addon_keymaps.append((km, kmi))


def theme_probe_keymap_item(context):
    keyconfigs = getattr(context.window_manager, "keyconfigs", None) if context else None
    for kc in (getattr(keyconfigs, "user", None), getattr(keyconfigs, "addon", None)):
        if kc is None:
            continue
        km = kc.keymaps.get("Window")
        if km is None:
            continue
        for kmi in km.keymap_items:
            if kmi.idname == THEMEPROBE_OT_probe.bl_idname:
                return kc, km, kmi
    return None, None, None


def update_shortcut_map_type(self, context):
    _kc, _km, kmi = theme_probe_keymap_item(context)
    if kmi is None:
        sync_keymaps()
        _kc, _km, kmi = theme_probe_keymap_item(context)
    if kmi is not None:
        kmi.map_type = self.shortcut_map_type


class THEMEPROBE_OT_probe(Operator):
    bl_idname = "theme_probe.probe"
    bl_label = "Theme Dictionary"
    bl_description = bilingual_tooltip("Probe the current UI area and list candidate theme colors", "\u63a2\u6d4b\u5f53\u524d UI \u533a\u57df\u5e76\u5217\u51fa\u5019\u9009\u4e3b\u9898\u989c\u8272")

    mouse_x: IntProperty(options={"SKIP_SAVE"})
    mouse_y: IntProperty(options={"SKIP_SAVE"})

    def invoke(self, context, event):
        self.mouse_x = event.mouse_x
        self.mouse_y = event.mouse_y
        return self.execute(context)

    def execute(self, context):
        ensure_snapshot()
        ensure_history_timer()
        if not probe_at_position(context, self.mouse_x, self.mouse_y):
            self.report({"WARNING"}, tr("No UI area found under cursor"))
            return {"CANCELLED"}
        if context.window_manager.theme_probe_mode == "SIMILAR":
            if not set_sample_color(context, _probe_runtime.get("sample_color"), refresh_list=True):
                update_similar_seed_from_candidates(_probe_runtime.get("candidates", []))
        populate_candidate_collection(context)
        bpy.ops.theme_probe.show_candidates("INVOKE_DEFAULT")
        return {"FINISHED"}


class THEMEPROBE_OT_edit_color(Operator):
    bl_idname = "theme_probe.edit_color"
    bl_label = "Edit Theme Color"
    bl_description = bilingual_tooltip("Edit the selected theme color with Blender's native color picker", "\u4f7f\u7528 Blender \u539f\u751f\u62fe\u8272\u5668\u7f16\u8f91\u9009\u4e2d\u7684\u4e3b\u9898\u989c\u8272")

    label_text: StringProperty()
    theme_path: StringProperty()

    def invoke(self, context, event):
        ensure_snapshot()
        ensure_history_timer()
        return context.window_manager.invoke_popup(self, width=440)

    def execute(self, context):
        tag_redraw_all()
        return {"FINISHED"}

    def check(self, context):
        tag_redraw_all()
        return True

    def draw(self, context):
        layout = self.layout
        owner, attr = resolve_theme_path(self.theme_path)
        layout.label(text=self.label_text or tr("Color"))
        layout.label(text=self.theme_path)
        if owner is None:
            layout.label(text=tr("This color field does not exist in the current Blender version."), icon="ERROR")
            return
        box = layout.box()
        box.use_property_split = True
        box.prop(owner, attr, text=tr("Color"))

    def cancel(self, context):
        tag_redraw_all()


class THEMEPROBE_OT_restore_session(Operator):
    bl_idname = "theme_probe.restore_session"
    bl_label = "Reset Current Theme"
    bl_description = bilingual_tooltip("Reset the current theme to the latest saved snapshot", "\u5c06\u5f53\u524d\u4e3b\u9898\u91cd\u7f6e\u4e3a\u6700\u65b0\u4fdd\u5b58\u7684\u5feb\u7167\u72b6\u6001")

    def execute(self, context):
        if restore_snapshot():
            self.report({"INFO"}, tr("Current theme has been reset"))
            return {"FINISHED"}
        self.report({"WARNING"}, tr("No session snapshot available"))
        return {"CANCELLED"}


class THEMEPROBE_OT_undo_theme_change(Operator):
    bl_idname = "theme_probe.undo_theme_change"
    bl_label = "Undo Theme Change"
    bl_description = bilingual_tooltip("Undo the last theme change recorded by Theme Dictionary", "\u64a4\u9500 Theme Dictionary \u8bb0\u5f55\u7684\u4e0a\u4e00\u6b21\u4e3b\u9898\u4fee\u6539")

    def execute(self, context):
        if undo_theme_change():
            self.report({"INFO"}, tr("Theme Probe change undone"))
            return {"FINISHED"}
        self.report({"WARNING"}, tr("No Theme Probe change history"))
        return {"CANCELLED"}


class THEMEPROBE_OT_redo_theme_change(Operator):
    bl_idname = "theme_probe.redo_theme_change"
    bl_label = "Redo Theme Change"
    bl_description = bilingual_tooltip("Redo the last undone theme change recorded by Theme Dictionary", "\u91cd\u505a Theme Dictionary \u4e0a\u6b21\u64a4\u9500\u7684\u4e3b\u9898\u4fee\u6539")

    def execute(self, context):
        if redo_theme_change():
            self.report({"INFO"}, tr("Theme Probe change redone"))
            return {"FINISHED"}
        self.report({"WARNING"}, tr("No Theme Probe redo history"))
        return {"CANCELLED"}


class THEMEPROBE_OT_open_theme_folder(Operator):
    bl_idname = "theme_probe.open_theme_folder"
    bl_label = "Open Theme Folder"
    bl_description = bilingual_tooltip("Open Blender's interface_theme preset folder", "\u6253\u5f00 Blender \u7684 interface_theme \u9884\u8bbe\u6587\u4ef6\u5939")

    def execute(self, context):
        folder = open_theme_preset_folder()
        self.report({"INFO"}, tr("Opened {folder}").format(folder=folder))
        return {"FINISHED"}


class THEMEPROBE_OT_pick_probe_target(Operator):
    bl_idname = "theme_probe.pick_probe_target"
    bl_label = "Pick Probe Target"
    bl_description = bilingual_tooltip("Pick a UI area or sample color for probing", "\u533a\u57df\u6a21\u5f0f\u4e0b\u91cd\u65b0\u63a2\u6d4b\u70b9\u51fb\u533a\u57df\uff1b\u76f8\u4f3c\u989c\u8272\u6a21\u5f0f\u4e0b\u4f7f\u7528\u70b9\u51fb\u533a\u57df\u989c\u8272\u4f5c\u4e3a\u6837\u672c")

    def invoke(self, context, event):
        if context.window_manager.theme_probe_mode == "SIMILAR":
            try:
                return bpy.ops.ui.eyedropper_color(
                    "INVOKE_DEFAULT",
                    prop_data_path="window_manager.theme_probe_sample_color",
                )
            except TypeError:
                return bpy.ops.ui.eyedropper_color(
                    "INVOKE_DEFAULT",
                    prop_data_path="bpy.context.window_manager.theme_probe_sample_color",
                )
        context.window.cursor_modal_set("EYEDROPPER")
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"}:
            context.window.cursor_modal_restore()
            return {"CANCELLED"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            context.window.cursor_modal_restore()
            if not probe_at_position(context, event.mouse_x, event.mouse_y):
                self.report({"WARNING"}, tr("No UI area found under cursor"))
                return {"CANCELLED"}
            if context.window_manager.theme_probe_mode == "SIMILAR":
                update_similar_seed_from_candidates(_probe_runtime.get("candidates", []))
            populate_candidate_collection(context)
            return {"FINISHED"}
        return {"RUNNING_MODAL"}


class THEMEPROBE_OT_toggle_candidate_selection(Operator):
    bl_idname = "theme_probe.toggle_candidate_selection"
    bl_label = "Toggle Candidate Selection"
    bl_description = bilingual_tooltip("Select or deselect this color candidate", "\u9009\u4e2d\u6216\u53d6\u6d88\u9009\u4e2d\u8be5\u989c\u8272\u5019\u9009\u9879")

    index: IntProperty(default=-1)

    def execute(self, context):
        wm = context.window_manager
        items = getattr(wm, "theme_probe_candidates", None)
        if _candidate_preview_auto_disabled_sync:
            stop_candidate_preview_from_mouse(context)
            tag_redraw_all()
            return {"FINISHED"}
        if getattr(wm, "theme_probe_candidate_preview_index", -1) == self.index:
            stop_candidate_preview_from_mouse(context)
        else:
            restore_candidate_preview()
            auto_disable_similar_sync_for_preview(context)
            wm.theme_probe_candidate_preview_index = self.index
            wm.theme_probe_candidate_index = self.index
            if items and 0 <= self.index < len(items):
                remember_candidate_choice(context, items[self.index].path, items[self.index].label)
            schedule_candidate_preview(context)
        tag_redraw_all()
        return {"FINISHED"}


class THEMEPROBE_OT_toggle_candidate_lock(Operator):
    bl_idname = "theme_probe.toggle_candidate_lock"
    bl_label = "Toggle Candidate Lock"
    bl_description = bilingual_tooltip("Lock or unlock this similar color candidate", "\u9501\u5b9a\u6216\u89e3\u9501\u8be5\u76f8\u4f3c\u8272\u5019\u9009\u9879")

    index: IntProperty(default=-1)

    def execute(self, context):
        wm = context.window_manager
        items = getattr(wm, "theme_probe_candidates", None)
        if not items or self.index < 0 or self.index >= len(items):
            return {"CANCELLED"}

        path = getattr(items[self.index], "path", "")
        if not path:
            return {"CANCELLED"}

        if candidate_path_locked(path):
            _locked_candidate_paths.discard(path)
        else:
            restore_candidate_preview()
            _locked_candidate_paths.add(path)
            if getattr(wm, "theme_probe_candidate_preview_index", -1) == self.index:
                wm.theme_probe_candidate_preview_index = -1
        tag_redraw_all()
        return {"FINISHED"}


class THEMEPROBE_OT_unlock_all_candidates(Operator):
    bl_idname = "theme_probe.unlock_all_candidates"
    bl_label = "Unlock All"
    bl_description = bilingual_tooltip("Clear every locked state in the Theme Dictionary list", "\u6e05\u9664 Theme Dictionary \u5217\u8868\u4e2d\u7684\u6240\u6709\u9501\u5b9a\u72b6\u6001")

    def execute(self, context):
        _locked_candidate_paths.clear()
        tag_redraw_all()
        return {"FINISHED"}


class THEMEPROBE_CandidateItem(PropertyGroup):
    label: StringProperty()
    path: StringProperty()
    section: StringProperty()
    number: IntProperty()


class THEMEPROBE_UL_candidates(UIList):
    bl_idname = "THEMEPROBE_UL_candidates"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        owner, attr = resolve_theme_path(item.path)
        column = layout.column(align=True)
        previous_section = ""
        if index > 0:
            try:
                previous_section = data.theme_probe_candidates[index - 1].section
            except Exception:
                previous_section = ""
        if item.section and item.section != previous_section:
            header = column.row(align=True)
            header.enabled = False
            header.label(text=item.section)
        row = column.row(align=False)
        if owner is None:
            row.label(text=f"{item.number}. {item.label}", icon="ERROR")
            return
        content_row = row
        locked = candidate_path_locked(item.path)
        if getattr(context.window_manager, "theme_probe_mode", "AREA") == "SIMILAR":
            lock_split = row.split(factor=0.13, align=False)
            lock_part = lock_split.row(align=True)
            lock_part.alignment = "CENTER"
            lock_op = lock_part.operator(
                THEMEPROBE_OT_toggle_candidate_lock.bl_idname,
                text="",
                icon=candidate_path_lock_icon(item.path),
                emboss=False,
            )
            lock_op.index = index
            content_row = lock_split.row(align=False)
            content_row.enabled = not locked
        split = content_row.split(factor=0.56, align=False)
        select_part = split.row(align=True)
        select_part.alignment = "CENTER"
        select_op = select_part.operator(
            THEMEPROBE_OT_toggle_candidate_selection.bl_idname,
            text=item.label,
            emboss=False,
        )
        select_op.index = index
        color_part = split.row(align=False)
        color_part.prop(owner, attr, text="")


class THEMEPROBE_OT_show_candidates(Operator):
    bl_idname = "theme_probe.show_candidates"
    bl_label = "Theme Dictionary Candidates"
    bl_description = bilingual_tooltip("Show a compact list of likely theme colors", "\u663e\u793a\u4e00\u4e2a\u7d27\u51d1\u7684\u5019\u9009\u4e3b\u9898\u989c\u8272\u5217\u8868")

    def invoke(self, context, event):
        prepare_candidate_collection(context)
        width = getattr(context.window_manager, "theme_probe_popup_width", POPUP_WIDTH)
        return context.window_manager.invoke_popup(self, width=width)

    def execute(self, context):
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        area_type = _probe_runtime.get("area_type", "UNKNOWN")
        region_type = _probe_runtime.get("region_type", "")
        zone = _probe_runtime.get("zone", "")
        boundary = _probe_runtime.get("boundary", {})
        wm = context.window_manager
        width = getattr(wm, "theme_probe_popup_width", POPUP_WIDTH)

        header = layout.row(align=True)
        header.operator(THEMEPROBE_OT_pick_probe_target.bl_idname, text="", icon="EYEDROPPER")
        if wm.theme_probe_mode == "SIMILAR":
            title = color_hex(_similar_seed_signature) or tr("No Sample")
        elif area_type == "SCREEN":
            title = display_zone_label(zone)
        else:
            title = f"{area_type} / {region_type or tr('NONE')}"
            sample_hex = color_hex(signature_from_color(_probe_runtime.get("sample_color")))
            if sample_hex:
                title = f"{title} {sample_hex}"
        if wm.theme_probe_mode == "SIMILAR":
            sample_factor = max(0.22, min(0.84, 178.0 / max(float(width), 1.0)))
            sample_split = header.split(factor=sample_factor, align=True)
            sample_row = sample_split.row(align=True)
            sample_width = max(float(width) * sample_factor, 1.0)
            label_target = 68.0 if width > 400 else 78.0
            label_factor = max(0.38, min(0.72, label_target / sample_width))
            compact_sample = sample_row.split(factor=label_factor, align=True)
            compact_sample.label(text=title)
            swatch = compact_sample.row(align=True)
            swatch.scale_x = 0.42
            swatch.prop(wm, "theme_probe_sample_color", text="")
            folder_row = sample_split.row(align=True)
            folder_row.alignment = "RIGHT"
            folder_row.operator(THEMEPROBE_OT_open_theme_folder.bl_idname, text="", icon="FILE_FOLDER")
        else:
            header.label(text=title)
            header.operator(THEMEPROBE_OT_open_theme_folder.bl_idname, text="", icon="FILE_FOLDER")
        if boundary.get("near_any"):
            layout.label(text=tr("Near Boundary"), icon="MOD_EDGESPLIT")

        layout.prop(wm, "theme_probe_mode", text=tr("Mode"))
        controls = layout.row(align=True)
        controls.prop(wm, "theme_probe_popup_width", text=tr("Width"))
        tolerance_row = controls.row(align=True)
        tolerance_row.enabled = wm.theme_probe_mode == "SIMILAR"
        tolerance_row.prop(wm, "theme_probe_tolerance", text=tr("Tolerance"), slider=True)
        if wm.theme_probe_mode == "SIMILAR":
            tools_row = layout.row(align=True)
            unlock_row = tools_row.row(align=True)
            unlock_row.operator(THEMEPROBE_OT_unlock_all_candidates.bl_idname, text=tr("Unlock All"), icon="UNLOCKED")
            sync_row = tools_row.row(align=True)
            sync_row.alignment = "RIGHT"
            sync_row.label(text=tr("Sync Changes"))
            sync_row.prop(wm, "theme_probe_sync_similar", text="")
        layout.separator()

        if not wm.theme_probe_candidates:
            layout.label(text=tr("No available candidates found"), icon="INFO")

        list_items = wm.theme_probe_candidates
        if list_items:
            layout.template_list(
                "THEMEPROBE_UL_candidates",
                "",
                wm,
                "theme_probe_candidates",
                wm,
                "theme_probe_candidate_index",
                rows=min(POPUP_LIST_ROWS, max(1, len(list_items))),
                maxrows=POPUP_LIST_ROWS,
            )
            schedule_candidate_preview(context)
        layout.separator()
        preset_row = layout.row(align=True)
        root = theme_root()
        filepath = current_theme_filepath()
        preset_label = os.path.splitext(os.path.basename(filepath))[0] if filepath else (getattr(root, "name", "") if root else tr("Presets"))
        preset_row.menu("USERPREF_MT_interface_theme_presets", text=preset_label or tr("Presets"))
        preset_row.operator("wm.interface_theme_preset_add", text="", icon="ADD")
        preset_row.operator("wm.interface_theme_preset_remove", text="", icon="REMOVE")
        if hasattr(bpy.ops.wm, "interface_theme_preset_save"):
            preset_row.operator("wm.interface_theme_preset_save", text="", icon="FILE_TICK")
        else:
            preset_row.label(text=tr("Use Blender native presets"), icon="INFO")

        footer = layout.row(align=True)
        footer.scale_y = 1.05
        footer.operator(
            THEMEPROBE_OT_restore_session.bl_idname,
            text=tr("Reset Current Theme"),
            icon="FILE_REFRESH",
        )
        footer.operator(
            THEMEPROBE_OT_undo_theme_change.bl_idname,
            text="",
            icon="BACK",
        )
        footer.operator(
            THEMEPROBE_OT_redo_theme_change.bl_idname,
            text="",
            icon="FORWARD",
        )


class THEMEPROBE_Preferences(AddonPreferences):
    bl_idname = ADDON_ID

    shortcut_map_type: EnumProperty(
        name="Shortcut Input",
        description=bilingual_tooltip("Choose whether the panel shortcut uses keyboard or mouse input", "\u9009\u62e9\u9762\u677f\u5feb\u6377\u952e\u4f7f\u7528\u952e\u76d8\u8fd8\u662f\u9f20\u6807\u8f93\u5165"),
        items=SHORTCUT_MAP_TYPES,
        default="KEYBOARD",
        update=update_shortcut_map_type,
    )

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        split = row.split(factor=0.43, align=True)
        assist_row = split.row(align=True)
        assist_row.label(text=tr("Use shortcut to bring up the panel in Blender"))
        shortcut_row = split.row(align=True)
        shortcut_row.alignment = "RIGHT"
        _kc, _km, kmi = theme_probe_keymap_item(context)
        if kmi is None:
            sync_keymaps()
            _kc, _km, kmi = theme_probe_keymap_item(context)
        if kmi is None:
            shortcut_row.label(text=tr("Shortcut not found. Please restart Blender."), icon="ERROR")
            return
        if kmi.map_type != self.shortcut_map_type:
            kmi.map_type = self.shortcut_map_type
        shortcut_row.prop(kmi, "active", text="", emboss=False)
        shortcut_row.label(text=tr("Panel Shortcut"))
        shortcut_row.separator(factor=2.5)
        shortcut_row.prop(self, "shortcut_map_type", text="")
        event_row = shortcut_row.row(align=True)
        event_row.scale_x = 0.67
        if kmi.map_type in {"KEYBOARD", "MOUSE"}:
            event_row.prop(kmi, "type", text="", full_event=True)
        else:
            kmi.map_type = self.shortcut_map_type
            event_row.prop(kmi, "type", text="", full_event=True)


ThemeProbeOperator = THEMEPROBE_OT_probe
ThemeProbePopup = THEMEPROBE_OT_show_candidates
ThemeProbePreferences = THEMEPROBE_Preferences


classes = (
    THEMEPROBE_OT_probe,
    THEMEPROBE_OT_edit_color,
    THEMEPROBE_OT_restore_session,
    THEMEPROBE_OT_undo_theme_change,
    THEMEPROBE_OT_redo_theme_change,
    THEMEPROBE_OT_open_theme_folder,
    THEMEPROBE_OT_pick_probe_target,
    THEMEPROBE_OT_toggle_candidate_selection,
    THEMEPROBE_OT_toggle_candidate_lock,
    THEMEPROBE_OT_unlock_all_candidates,
    THEMEPROBE_CandidateItem,
    THEMEPROBE_UL_candidates,
    THEMEPROBE_OT_show_candidates,
    THEMEPROBE_Preferences,
)


def register():
    if translation is not None:
        translation.register()
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.theme_probe_candidates = CollectionProperty(type=THEMEPROBE_CandidateItem)
    bpy.types.WindowManager.theme_probe_candidate_index = IntProperty(default=0, min=-1, update=update_candidate_index)
    bpy.types.WindowManager.theme_probe_candidate_preview_index = IntProperty(default=-1, min=-1)
    bpy.types.WindowManager.theme_probe_mode = EnumProperty(
        name="",
        description=bilingual_tooltip("Choose how Theme Dictionary searches for candidate colors", "\u9009\u62e9 Theme Dictionary \u68c0\u7d22\u5019\u9009\u989c\u8272\u7684\u65b9\u5f0f"),
        items=PROBE_MODE_ITEMS,
        default="AREA",
        update=update_probe_list_settings,
    )
    bpy.types.WindowManager.theme_probe_tolerance = IntProperty(
        name="Tolerance",
        default=SIMILAR_TOLERANCE_DEFAULT,
        min=0,
        max=255,
        description=bilingual_tooltip("Set the tolerance for similar color search", "\u8bbe\u7f6e\u76f8\u4f3c\u989c\u8272\u68c0\u7d22\u7684\u5bb9\u5dee"),
        update=update_probe_list_settings,
    )
    bpy.types.WindowManager.theme_probe_sync_similar = BoolProperty(
        name="Sync Changes",
        description=bilingual_tooltip("Sync edits to all unlocked similar color candidates", "\u540c\u6b65\u4fee\u6539\u6240\u6709\u672a\u9501\u5b9a\u7684\u76f8\u4f3c\u8272\u5019\u9009\u9879"),
        default=True,
    )
    bpy.types.WindowManager.theme_probe_popup_width = IntProperty(
        name="Popup Width",
        default=POPUP_WIDTH,
        min=160,
        max=720,
        description=bilingual_tooltip("Reopen the panel after changing this width", "\u62d6\u52a8\u6570\u503c\u540e\u91cd\u65b0\u547c\u51fa\u9762\u677f\u751f\u6548"),
    )
    bpy.types.WindowManager.theme_probe_sample_color = FloatVectorProperty(
        name="Sample Color",
        description=bilingual_tooltip("Sample color used for similar color search", "\u7528\u4e8e\u76f8\u4f3c\u989c\u8272\u68c0\u7d22\u7684\u53d6\u6837\u989c\u8272"),
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
        update=update_sample_color,
    )
    sync_keymaps()
    ensure_history_timer()


def unregister():
    restore_candidate_preview()
    _locked_candidate_paths.clear()
    stop_history_timer()
    while addon_keymaps:
        km, kmi = addon_keymaps.pop()
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    stop_history_timer()
    for prop_name in (
        "theme_probe_tolerance",
        "theme_probe_sync_similar",
        "theme_probe_mode",
        "theme_probe_popup_width",
        "theme_probe_sample_color",
        "theme_probe_candidate_preview_index",
        "theme_probe_candidate_index",
        "theme_probe_candidates",
    ):
        if hasattr(bpy.types.WindowManager, prop_name):
            delattr(bpy.types.WindowManager, prop_name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    if translation is not None:
        translation.unregister()


if __name__ == "__main__":
    register()
