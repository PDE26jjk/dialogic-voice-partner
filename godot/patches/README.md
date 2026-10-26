# Dialogic voice event patch

Dialogic's stock `DialogicVoiceEvent` has no identity field, so a line cannot be
matched reliably after the timeline is edited or reordered. This patch adds one
exported property and one shortcode parameter:

```gdscript
@export var voice_partner_uuid := ""
# ...
"uuid": {"property": "voice_partner_uuid", "default": ""}
```

which serializes as:

```
[voice path="res://..." volume="0" bus="Master" uuid="0b6f..."]
```

## Apply

```powershell
powershell -ExecutionPolicy Bypass -File scripts/apply-dialogic-voice-patch.ps1 -GodotProject "R:\path\to\godot\project"
```

The script backs up the original file to `event_voice.gd.bak` next to it, then
copies this patch over it. Restart the Godot editor afterwards (or disable and
re-enable the Dialogic plugin).

## Manual apply

Copy `godot/patches/event_voice.gd` over:

```
<godot project>/addons/dialogic/Modules/Voice/event_voice.gd
```

## Caveats

- Updating Dialogic overwrites this file; re-apply the patch after an update.
- The patch changes a vendored addon. Keep it in your own VCS branch or re-apply
  it from this repo — do not commit the whole Dialogic checkout to this project.
- Timelines written before the patch have no `uuid`; the dock generates and saves
  one the first time it loads such a timeline.
