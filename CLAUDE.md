# Conduit — Developer Notes for Claude

## Encode Settings Parity Rule

**Every encoding option must exist in all three surfaces:**

1. **Settings menu** — global defaults (Video / Audio / Subtitles / Encoder tabs)
2. **Encode modal** — per-batch overrides (opened via the Encode button)
3. **Preset editor** — saved named presets (Settings → Presets tab)

If you add a new encode field anywhere, add it to all three. If you remove one, remove it everywhere.

### Authoritative field list (15 fields)

| Field               | Settings element ID          | Encode modal element ID   | Preset editor element ID  |
|---------------------|------------------------------|---------------------------|---------------------------|
| `hw_encoder`        | `settings-hw-encoder`        | `ce-hw-encoder`           | `pe-hw-encoder`           |
| `output_video_codec`| `settings-output-codec`      | `ce-output-codec`         | `pe-output-codec`         |
| `video_quality_cq`  | `settings-cq`                | `ce-cq`                   | `pe-cq`                   |
| `audio_lossy_action`| `settings-audio-action`      | `ce-audio-action`         | `pe-audio-action`         |
| `output_container`  | `settings-container`         | `ce-container`            | `pe-container`            |
| `scale_height`      | `settings-scale-height`      | `ce-scale-height`         | `pe-scale-height`         |
| `pix_fmt`           | `settings-pix-fmt`           | `ce-pix-fmt`              | `pe-pix-fmt`              |
| `encoder_speed`     | `settings-encoder-speed`     | `ce-encoder-speed`        | `pe-encoder-speed`        |
| `subtitle_mode`     | `settings-subtitle-mode`     | `ce-subtitle-mode`        | `pe-subtitle-mode`        |
| `force_stereo`      | `settings-force-stereo`      | `ce-force-stereo`         | `pe-force-stereo`         |
| `audio_normalize`   | `settings-audio-normalize`   | `ce-audio-normalize`      | `pe-audio-normalize`      |
| `fps_cap`           | `settings-fps-cap`           | `ce-fps-cap`              | `pe-fps-cap`              |
| `deinterlace`       | `settings-deinterlace`       | `ce-deinterlace`          | `pe-deinterlace`          |
| `autocrop`          | `settings-autocrop`          | `ce-autocrop`             | `pe-autocrop`             |
| `denoise`           | `settings-denoise`           | `ce-denoise`              | `pe-denoise`              |
| `force_encode_audio`| `settings-force-encode-audio`| `ce-force-encode-audio`   | `pe-force-encode-audio`   |
| `extra_args`        | `settings-extra-args`        | `ce-extra-args`           | `pe-extra-args`           |

### Checklist when adding a new encode field

- [ ] Add HTML element to **Settings** (appropriate tab: Video / Audio / Subtitles / Encoder)
- [ ] Add HTML element to **Encode modal** (`custom-encode-modal`)
- [ ] Add HTML element to **Preset editor** (`preset-editor`)
- [ ] Add to `UpdateSettingsRequest` model in `main.py`
- [ ] Add to `AddJobsRequest` model in `main.py`
- [ ] Add to `PresetRequest` model in `main.py`
- [ ] Add to `get_settings()` response in `main.py`
- [ ] Add to `update_settings()` handler in `main.py`
- [ ] Add to `create_preset()` / `update_preset()` in `main.py`
- [ ] Add to `create_jobs()` INSERT in `main.py`
- [ ] Add DB column migration in `database.py`
- [ ] Add encoder global + `set_encode_options()` param in `encoder.py`
- [ ] Add to `openSettingsModal` (load) and `saveSettings` (save) in `app.js`
- [ ] Add to `_ceApplySettings` in `app.js` — marked `// ENCODE PARITY`
- [ ] Add to `handleCustomEncode` settings fetch block in `app.js` — marked `// ENCODE PARITY`
- [ ] Add to `_doSubmitCustomEncode` overrides in `app.js`
- [ ] Add to `_openPresetEditor` (load/reset) in `app.js` — marked `// ENCODE PARITY`
- [ ] Add to `_savePreset` payload in `app.js` — marked `// ENCODE PARITY`

### Settings menu tab layout

The settings modal uses a **left sidebar** of stacked tabs (not a horizontal tab bar).
Tabs in order: Encoder · Video · Audio · Subtitles · Flagging · Presets · Database · Network

When adding a new field, place it in the most appropriate existing tab rather than creating a new tab unless the field clearly belongs to a new logical category.

### Toggle switches

Use the `.ce-toggle-item` / `.ce-toggle-label` pattern for all toggle checkboxes — both in the encode modal and preset editor. Do **not** apply inline styles to `.toggle-switch` or `.toggle-track`; their layout depends on `position: absolute; inset: 0` within a fixed 38×22px relative parent.

```html
<label class="ce-toggle-item">
  <span class="toggle-switch"><input type="checkbox" id="FIELD-ID"><span class="toggle-track"><span class="toggle-thumb"></span></span></span>
  <span class="ce-toggle-label">Label Text</span>
</label>
```

## Drag-and-Drop

Files and folders can be dropped onto the Conduit window. The drop flow:

1. **Drag over** → full-screen `#drop-overlay` appears
2. **Drop** → paths extracted from `e.dataTransfer.files[i].path` (webkit2gtk extension)
3. **`POST /api/resolve-drops`** → resolves paths to DB file records; new files are probed with ffprobe and inserted into the virtual `__dropped__` folder (path `"__dropped__"`, filtered from the folders UI)
4. **`#drop-choice-modal`** → user picks "Custom Encode" (opens `#custom-encode-modal` with resolved files) or "Optimize" (queues with global settings)

`handleCustomEncode(filesOverride)` accepts an optional file list; if passed, uses it instead of `state.selectedIds`.

The `__dropped__` folder is excluded from `GET /api/folders` via a `WHERE f.path != '__dropped__'` filter.
