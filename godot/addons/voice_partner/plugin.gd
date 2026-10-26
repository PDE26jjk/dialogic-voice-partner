@tool
extends EditorPlugin

## Adds a dock that pushes the voice lines of the currently open Dialogic
## timeline to the Voice Partner desktop service.

const DockScript := preload("res://addons/voice_partner/voice_partner_dock.gd")

var _dock: Control


func _enter_tree() -> void:
	_dock = DockScript.new()
	_dock.name = "Voice Partner"
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)


func _exit_tree() -> void:
	if _dock:
		remove_control_from_docks(_dock)
		_dock.queue_free()
		_dock = null
