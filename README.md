## Bundle channels from several cycles into single file or one file per cycle

### Command line arguments

**`-m`**    path to cycle map file YAML \
**`-o`**    directory to output combined images \
**`-p`**    parameters how to bundle images: separate, combine. separate - each cycle in a separate file, combine - all cycles combined in one file.

### Example usage
`python bundle.py -m cycle_map.yaml -o output_dir -p combine`

### Output naming
`separate`: cycle01.tif, cycle02.tif ... -- one file for each cycle
`combine`: cycles_combined.tif -- one file

### Requirements
`tifffile PyYAML`