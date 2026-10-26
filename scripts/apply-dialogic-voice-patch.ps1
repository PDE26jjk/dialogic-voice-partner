param(
    [Parameter(Mandatory = $true)]
    [string]$GodotProject
)

$source = Join-Path $PSScriptRoot '..\godot\patches\event_voice.gd'
$source = (Resolve-Path $source).Path
$target = Join-Path $GodotProject 'addons\dialogic\Modules\Voice\event_voice.gd'

if (-not (Test-Path $target)) {
    throw "No Dialogic voice event at $target. Point -GodotProject at the Godot project root."
}

Copy-Item $target "$target.bak" -Force
Copy-Item $source $target -Force

Write-Output "Patched: $target"
Write-Output "Backup:  $target.bak"
Write-Output "Restart the Godot editor (or reload the Dialogic plugin) to pick up the new uuid field."
