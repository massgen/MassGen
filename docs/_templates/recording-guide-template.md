# Recording Guide: {FEATURE_NAME} (v{VERSION})

**Case Study:** {CASE_STUDY_NAME}

**Estimated Recording Time:** {ESTIMATED_TIME} minutes

**Recommended Tool:** QuickTime Player (macOS) / OBS Studio (Cross-platform)

---

## Pre-Recording Checklist

### Environment Setup

- [ ] Clean terminal with no previous command history visible
- [ ] Terminal color scheme: {COLOR_SCHEME} (recommended for readability)
- [ ] Font size: {FONT_SIZE}pt minimum for screen recording
- [ ] Close unnecessary applications and notifications
- [ ] Clear desktop (hide icons if possible)
- [ ] Prepare all test files in designated directory

### Test Data Preparation

**Working Directory:** `{WORKING_DIR}`

**Files Needed:**
```bash
{WORKING_DIR}/
├── {FILE_1}
├── {FILE_2}
├── {FILE_3}
└── config/
    └── {CONFIG_FILE}
```

**Prepare Files:**
```bash
# Create working directory
mkdir -p {WORKING_DIR}/config

# Create test files
{FILE_CREATION_COMMANDS}
```

### Configuration Verification

**Test Configuration:**
```bash
# Verify configuration is valid
uv run python -c "import yaml; yaml.safe_load(open('{CONFIG_FILE}'))"
```

**API Keys:**
- [ ] All required API keys set in environment
- [ ] Test API connection before recording

### Dry Run

- [ ] Run through the entire demo once without recording
- [ ] Time each step to ensure pacing
- [ ] Verify all commands work as expected
- [ ] Check that outputs are clear and readable

---

## Recording Segments

### Segment 1: Introduction (0:00-0:30)

**Shot:** Terminal window with title

**Script:**
```
"Welcome to the v{VERSION} release demonstration.
In this video, we'll explore {FEATURE_NAME}, which {FEATURE_DESCRIPTION}.
Let's see it in action."
```

**Actions:**
1. Show clean terminal
2. Display MassGen version:
   ```bash
   massgen --version
   ```
3. Brief pause for version to be visible (2 seconds)

**Camera Notes:**
- Full terminal window visible
- Version number clearly readable

**Captions:**
```
[00:00] MassGen v{VERSION} Demonstration
[00:05] Feature: {FEATURE_NAME}
[00:10] {FEATURE_TAGLINE}
```

---

### Segment 2: Setup and Configuration (0:30-1:30)

**Shot:** Terminal and config file side-by-side (if possible)

**Script:**
```
"First, let's set up our configuration. We'll use {EXAMPLE_SCENARIO} as our test case."
```

**Actions:**
1. Show configuration file:
   ```bash
   cat config/{CONFIG_FILE}
   ```
2. Pause to let viewers read config (5 seconds)
3. Explain key settings:
   ```bash
   # Highlight these lines in the video edit
   {KEY_CONFIG_LINE_1}
   {KEY_CONFIG_LINE_2}
   {KEY_CONFIG_LINE_3}
   ```

**Camera Notes:**
- Config should be readable
- Use syntax highlighting if possible
- Zoom if text is too small

**Captions:**
```
[00:30] Configuration Setup
[00:45] {CONFIG_EXPLANATION_1}
[01:00] {CONFIG_EXPLANATION_2}
[01:15] Ready to run
```

---

### Segment 3: Feature Execution (1:30-3:00)

**Shot:** Terminal window, full screen

**Script:**
```
"Now let's run MassGen with our new {FEATURE_NAME} feature."
```

**Actions:**
1. Show the command before running:
   ```bash
   # Type this slowly so viewers can follow
   {MAIN_COMMAND}
   ```
2. Pause (2 seconds) before pressing Enter
3. Execute command
4. Show progress indicators
5. Highlight interesting output

**Camera Notes:**
- Ensure all output is visible
- If output scrolls too fast, slow down terminal output or record in sections
- Zoom in on key metrics/results

**Important Timing:**
- If command takes > 30 seconds, consider time-lapse or cut
- Keep raw footage for detailed documentation

**Captions:**
```
[01:30] Running MassGen
[01:45] {PROGRESS_NOTE_1}
[02:15] {PROGRESS_NOTE_2}
[02:45] {RESULT_SUMMARY}
```

---

### Segment 4: Results Analysis (3:00-4:00)

**Shot:** Terminal with results

**Script:**
```
"Let's examine the results. Notice {KEY_OBSERVATION_1} and {KEY_OBSERVATION_2}."
```

**Actions:**
1. Scroll through output slowly
2. Highlight key results:
   ```bash
   # Show specific result files
   cat {RESULT_FILE_1}
   ```
3. Demonstrate metrics/improvements:
   ```bash
   {METRICS_COMMAND}
   ```

**Camera Notes:**
- Zoom in on important numbers
- Use arrow cursor to point at key information
- Pause on important screens (3-5 seconds each)

**Captions:**
```
[03:00] Results Analysis
[03:15] {METRIC_1}: {VALUE_1}
[03:30] {METRIC_2}: {VALUE_2}
[03:45] {IMPROVEMENT_SUMMARY}
```

---

### Segment 5: Advanced Usage (4:00-5:00)

**Shot:** Terminal, possibly split screen

**Script:**
```
"The {FEATURE_NAME} feature also supports {ADVANCED_CAPABILITY}."
```

**Actions:**
1. Show advanced command:
   ```bash
   {ADVANCED_COMMAND}
   ```
2. Demonstrate additional options:
   ```bash
   {OPTION_COMMAND_1}
   {OPTION_COMMAND_2}
   ```

**Camera Notes:**
- Keep pace moderate
- Ensure all commands are visible long enough to read

**Captions:**
```
[04:00] Advanced Features
[04:20] {ADVANCED_FEATURE_1}
[04:40] {ADVANCED_FEATURE_2}
```

---

### Segment 6: Comparison (5:00-6:00)

**Shot:** Side-by-side or before/after comparison

**Script:**
```
"Let's compare this with the previous version to see the improvements."
```

**Actions:**
1. Show old way (if applicable):
   ```bash
   # Old approach
   {OLD_COMMAND}
   ```
2. Show new way:
   ```bash
   # New approach with v{VERSION}
   {NEW_COMMAND}
   ```
3. Compare results side-by-side

**Camera Notes:**
- Clear visual distinction between old and new
- Use different terminal windows if needed

**Captions:**
```
[05:00] Before vs. After
[05:20] Previous version: {OLD_RESULT}
[05:40] New version: {NEW_RESULT}
[05:50] Improvement: {IMPROVEMENT_PERCENTAGE}
```

---

### Segment 7: Conclusion (6:00-6:30)

**Shot:** Return to clean terminal or show final results

**Script:**
```
"This demonstrates the new {FEATURE_NAME} in MassGen v{VERSION}.
Key improvements include {IMPROVEMENT_1}, {IMPROVEMENT_2}, and {IMPROVEMENT_3}.
Try it yourself with 'pip install massgen=={VERSION}'."
```

**Actions:**
1. Show installation command:
   ```bash
   pip install massgen=={VERSION}
   ```
2. Display documentation link
3. Fade to black

**Captions:**
```
[06:00] Summary
[06:10] {IMPROVEMENT_1}
[06:15] {IMPROVEMENT_2}
[06:20] {IMPROVEMENT_3}
[06:25] Install: pip install massgen=={VERSION}
```

---

## Post-Recording Checklist

### Video Files

- [ ] Raw footage saved: `video/raw/demo-raw.mov`
- [ ] Backup copy created
- [ ] Check video quality (resolution, clarity)
- [ ] Check audio quality (if narration recorded)

### Video Editing Tasks

- [ ] Trim beginning and end
- [ ] Add captions at specified timestamps
- [ ] Add zoom effects on important sections
- [ ] Speed up long-running commands (optional)
- [ ] Add transition effects between segments
- [ ] Add title card
- [ ] Add end card with links

### Caption File

- [ ] Export .srt caption file
- [ ] Save to `video/captions.srt`
- [ ] Verify caption timing

### Export Settings

**Recommended Export Settings:**
- **Format:** MP4 (H.264)
- **Resolution:** 1920x1080 or 1280x720
- **Frame Rate:** 30fps
- **Bitrate:** 5-8 Mbps
- **Audio:** AAC, 128-192 kbps

**Export Files:**
- `video/demo.mp4` - Main video
- `video/demo-hq.mp4` - High quality version (optional)
- `video/captions.srt` - Subtitles

---

## Troubleshooting Common Issues

### Video Issues

**Problem:** Text too small to read
**Solution:** Increase terminal font size to {RECOMMENDED_FONT_SIZE}pt, use zoom effects in editing

**Problem:** Command output scrolls too fast
**Solution:** Use `| less` or record in segments, edit out wait times

**Problem:** Video file too large
**Solution:** Reduce bitrate, use H.264 codec, consider shorter segments

### Technical Issues

**Problem:** Command fails during recording
**Solution:** Keep recording, fix issue, note timestamp for editing. Document in improvements.md

**Problem:** Unexpected output
**Solution:** Continue recording, document for case study insights

**Problem:** System notification appears
**Solution:** Enable "Do Not Disturb" mode before recording, edit out in post-production

---

## Tips for Great Demo Videos

### General Tips

1. **Pacing:** Allow 2-3 seconds after each command for viewers to read
2. **Cursor:** Keep cursor visible but not distracting
3. **Commands:** Type important commands on screen (don't paste)
4. **Pauses:** Brief pauses help viewers follow along
5. **Zoom:** Zoom in on key information (do in post-production)

### Terminal Tips

1. Use a clean, simple terminal theme
2. Increase font size (18-20pt recommended)
3. Use syntax highlighting when possible
4. Keep prompt simple: `$ ` or `massgen$ `
5. Clear screen between major sections

### Narration Tips (if recording audio)

1. Write script beforehand
2. Speak slowly and clearly
3. Pause between sentences
4. Re-record segments if needed
5. Use noise reduction in post-production

---

## Video Script Template

**Full narration script for video editor:**

```
[00:00-00:10]
"Welcome to the MassGen version {VERSION} demonstration.
Today we'll explore {FEATURE_NAME}."

[00:10-00:30]
"{FEATURE_DESCRIPTION}. This feature {KEY_BENEFIT}."

[00:30-01:00]
"Let's start by looking at the configuration.
Here you can see we're using {CONFIG_DETAIL_1} and {CONFIG_DETAIL_2}."

[01:00-01:30]
"Now we'll run MassGen with the following command: {COMMAND}.
Notice the {COMMAND_OPTION} flag, which enables {OPTION_PURPOSE}."

[01:30-03:00]
"As MassGen runs, you can see {PROGRESS_INDICATOR}.
{INTERESTING_OBSERVATION_1}. And here {INTERESTING_OBSERVATION_2}."

[03:00-04:00]
"The results show {RESULT_SUMMARY}.
{METRIC_1} improved by {IMPROVEMENT_1}.
{METRIC_2} improved by {IMPROVEMENT_2}."

[04:00-05:00]
"The feature also supports {ADVANCED_CAPABILITY}.
This allows you to {ADVANCED_BENEFIT}."

[05:00-06:00]
"Compared to the previous version, we see {COMPARISON_SUMMARY}.
This represents a {OVERALL_IMPROVEMENT} improvement."

[06:00-06:30]
"To try this yourself, install with pip install massgen equals {VERSION}.
Visit the documentation at {DOCS_LINK} for more information.
Thank you for watching."
```

---

## File Organization

After completing the recording and editing:

```
docs/releases/v{VERSION}/
├── video/
│   ├── demo.mp4              # Final edited video
│   ├── demo-hq.mp4           # High quality version (optional)
│   ├── captions.srt          # Subtitle file
│   ├── thumbnail.png         # Video thumbnail
│   ├── raw/                  # Raw footage (keep for re-editing)
│   │   ├── segment-1.mov
│   │   ├── segment-2.mov
│   │   └── ...
│   └── assets/               # Editing assets
│       ├── title-card.png
│       ├── end-card.png
│       └── music.mp3 (if used)
├── RECORDING_GUIDE.md        # This file
├── video-script.md           # Complete narration script
├── case-study.md             # Case study with video references
└── release-notes.md          # Release notes
```

---

## Review Checklist

Before publishing:

- [ ] Video plays correctly
- [ ] All captions are accurate and timed correctly
- [ ] Audio levels are consistent
- [ ] No sensitive information visible (API keys, etc.)
- [ ] All commands shown are reproducible
- [ ] Video demonstrates claimed improvements
- [ ] Video length is appropriate (5-8 minutes ideal)
- [ ] Thumbnail is attractive and descriptive
- [ ] File sizes are reasonable for web hosting

---

*This recording guide is part of MassGen's case study process. It ensures consistent, high-quality demonstration videos for each release.*

**Questions?** Ask in #documentation channel or refer to previous case studies in `docs/case_studies/`.
