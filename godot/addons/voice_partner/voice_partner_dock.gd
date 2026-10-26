@tool
extends VBoxContainer

## Dock that lists the voice lines of the currently open Dialogic timeline and
## pushes the selected ones to the Voice Partner service.

const DEFAULT_URL := "http://127.0.0.1:3900"
const SETTING_URL := "voice_partner/server_url"
const SETTING_ROOT := "voice_partner/project_root"
const UUID_FIELD := "voice_partner_uuid"

var _url_edit: LineEdit
var _root_edit: LineEdit
var _list: VBoxContainer
var _status: Label
var _push_button: Button
var _refresh_button: Button
var _http: HTTPRequest
var _entries: Array[Dictionary] = []
var _current_dtl := ""
var _pending_lines := 0


func _ready() -> void:
	_build_ui()
	_http = HTTPRequest.new()
	add_child(_http)
	_http.request_completed.connect(_on_request_completed)
	_refresh()


func _build_ui() -> void:
	add_theme_constant_override("separation", 6)

	var title := Label.new()
	title.text = "Voice Partner"
	add_child(title)

	var url_row := HBoxContainer.new()
	url_row.add_child(_make_label("Server"))
	_url_edit = LineEdit.new()
	_url_edit.text = str(_editor_setting(SETTING_URL, DEFAULT_URL))
	_url_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_url_edit.text_changed.connect(func(_text: String) -> void: _save_settings())
	url_row.add_child(_url_edit)
	add_child(url_row)

	var root_row := HBoxContainer.new()
	root_row.add_child(_make_label("Project"))
	_root_edit = LineEdit.new()
	_root_edit.text = str(_editor_setting(SETTING_ROOT, ""))
	_root_edit.placeholder_text = "Partner project folder"
	_root_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_root_edit.text_changed.connect(func(_text: String) -> void: _save_settings())
	root_row.add_child(_root_edit)
	add_child(root_row)

	var buttons := HBoxContainer.new()
	_refresh_button = Button.new()
	_refresh_button.text = "Refresh"
	_refresh_button.pressed.connect(_refresh)
	buttons.add_child(_refresh_button)
	_push_button = Button.new()
	_push_button.text = "Push selected"
	_push_button.pressed.connect(_push_selected)
	buttons.add_child(_push_button)
	add_child(buttons)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.custom_minimum_size = Vector2(0, 150)
	add_child(scroll)

	_list = VBoxContainer.new()
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_list.add_theme_constant_override("separation", 2)
	scroll.add_child(_list)

	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_status)


func _make_label(text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.custom_minimum_size = Vector2(58, 0)
	return label


func _editor_setting(key: String, default_value: Variant) -> Variant:
	if not Engine.is_editor_hint():
		return default_value
	var settings := EditorInterface.get_editor_settings()
	if settings.has_setting(key):
		return settings.get_setting(key)
	return default_value


func _save_settings() -> void:
	if not Engine.is_editor_hint():
		return
	var settings := EditorInterface.get_editor_settings()
	settings.set_setting(SETTING_URL, _url_edit.text.strip_edges())
	settings.set_setting(SETTING_ROOT, _root_edit.text.strip_edges())


func _refresh() -> void:
	_entries.clear()
	_current_dtl = ""
	for child in _list.get_children():
		child.queue_free()

	var path := str(DialogicUtil.get_editor_setting("current_timeline_path", ""))
	if path.is_empty():
		_set_status("Open a Dialogic timeline first.")
		return
	var timeline: DialogicTimeline = load(path)
	if timeline == null:
		_set_status("Could not load %s" % path)
		return
	_current_dtl = path

	var generated := false
	var events: Array = timeline.events
	for index in range(events.size()):
		var event: Variant = events[index]
		if not (event is DialogicVoiceEvent):
			continue
		if not (UUID_FIELD in event):
			_set_status("Voice event has no uuid field. Apply godot/patches/event_voice.gd first.")
			return

		var uuid := str(event.get(UUID_FIELD))
		if uuid.is_empty():
			uuid = _generate_uuid()
			event.set(UUID_FIELD, uuid)
			generated = true

		var text := ""
		var character := ""
		var character_name := ""
		var next_event: Variant = events[index + 1] if index + 1 < events.size() else null
		if next_event is DialogicTextEvent:
			text = next_event.text
			character = next_event.character_identifier
			if next_event.character:
				character_name = next_event.character.display_name

		var entry := {
			"uuid": uuid,
			"character": character,
			"character_name": character_name,
			"text": text,
			"selected": true,
		}
		_entries.append(entry)
		_add_row(entry)

	if generated:
		ResourceSaver.save(timeline, path)
		_set_status("%d line(s) loaded; new UUIDs saved to the timeline." % _entries.size())
	else:
		_set_status("%d voice line(s) in %s" % [_entries.size(), path.get_file()])


func _add_row(entry: Dictionary) -> void:
	var row := HBoxContainer.new()
	var check := CheckBox.new()
	check.button_pressed = true
	check.toggled.connect(func(pressed: bool) -> void: entry["selected"] = pressed)
	row.add_child(check)

	var label := Label.new()
	label.text = "%s: %s" % [_entry_speaker(entry), _shorten(str(entry.get("text", "")))]
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(label)

	_list.add_child(row)


func _entry_speaker(entry: Dictionary) -> String:
	var name_text := str(entry.get("character_name", ""))
	if name_text.is_empty():
		name_text = str(entry.get("character", ""))
	if name_text.is_empty():
		name_text = "Narrator"
	return name_text


func _shorten(text: String, limit: int = 46) -> String:
	var clean := text.replace("\n", " ").strip_edges()
	if clean.length() <= limit:
		return clean
	return clean.substr(0, limit) + "…"


func _generate_uuid() -> String:
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	return "%08x-%08x-%08x-%08x" % [rng.randi(), rng.randi(), rng.randi(), rng.randi()]


func _push_selected() -> void:
	var lines: Array = []
	for entry in _entries:
		if entry.get("selected", false):
			lines.append({
				"uuid": entry["uuid"],
				"character": entry["character"],
				"character_name": entry["character_name"],
				"text": entry["text"],
			})

	if lines.is_empty():
		_set_status("Select at least one line.")
		return

	var project_root := _root_edit.text.strip_edges()
	if project_root.is_empty():
		_set_status("Set the Partner project folder first.")
		return

	var payload := {"project_root": project_root, "dtl": _current_dtl, "lines": lines}
	var url := _url_edit.text.strip_edges().trim_suffix("/") + "/sync/lines"
	var error := _http.request(
		url,
		["Content-Type: application/json"],
		HTTPClient.METHOD_POST,
		JSON.stringify(payload)
	)
	if error != OK:
		_set_status("Could not start the request (%d)." % error)
		return

	_push_button.disabled = true
	_pending_lines = lines.size()
	_set_status("Pushing %d line(s)..." % lines.size())


func _on_request_completed(
	result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray
) -> void:
	_push_button.disabled = false
	if result != HTTPRequest.RESULT_SUCCESS:
		_set_status("Service unreachable (result %d). Is Voice Partner running?" % result)
		return
	if response_code != 200:
		_set_status("Service returned %d: %s" % [response_code, body.get_string_from_utf8()])
		return

	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	if typeof(parsed) == TYPE_DICTIONARY:
		var data: Dictionary = parsed
		_set_status("Pushed %d line(s): %d created, %d updated (section %s)." % [
			_pending_lines,
			int(data.get("created", 0)),
			int(data.get("updated", 0)),
			str(data.get("section", "?")),
		])
	else:
		_set_status("Pushed %d line(s)." % _pending_lines)


func _set_status(text: String) -> void:
	if _status:
		_status.text = text
