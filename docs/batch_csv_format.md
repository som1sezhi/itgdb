# Batch CSV format

In the Pack section of the admin site, there is an option to upload a batch of packs at once. The batch upload process takes in tabular data formatted as a CSV file. This data contains information about the packs to be uploaded, alongside URLs that ITGdb can use to download the packs.

## Example data and CSV file

| name | author | release_date | category | tags | source_link | label1 | link1 | label2 | link2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Pack A | Author A | 2025-01-01 | Stream |  | https://example.com/pack_a.zip |  | https://example.com/pack_a.zip |  |  |
| Pack B | Author B | 2023 | All Around | Compilation,DDR Scale | https://example.com/pack_b.zip | Pack page | https://example.com/pack_b_info | Songwheel | https://www.youtube.com/watch?v=xvFZjo5PgG0 |

```
name,author,release_date,category,tags,source_link,label1,link1,label2,link2
Pack A,Author A,2025-01-01,Stream,,https://example.com/pack_a.zip,,https://example.com/pack_a.zip,,
Pack B,Author B,2023,All Around,"Compilation,DDR Scale",https://example.com/pack_b.zip,Pack page,https://example.com/pack_b_info,Songwheel,https://www.youtube.com/watch?v=xvFZjo5PgG0
```

## Header row

```
name,author,release_date,category,tags,source_link,label1,link1,label2,link2
```

The header row is required to be included in the CSV, but its contents don't actually matter since it's skipped during parsing. It's here mainly for convenience reasons; I use Google Sheets to compile the data together, where the header row is useful for labelling columns, and it's nice to not have to delete it before exporting the sheet to CSV.

## Data rows

Each row after the header consists of at least 6 comma-separated values (corresponding to columns `name`, `author`, `release_date`, `category`, `tags`, `source_link`), and usually some number of values afterwards (corresponding to columns `label1`, `link1`, `label2`, `link2`, etc.). With the exception of `source_link`, all of these values are allowed be blank.

Note that values containing commas can be escaped in the CSV format by wrapping the value in double quotes. This is already handled for you if you use Google Sheets to export your data to CSV.

### `name`

The name of the pack. If blank, this will be auto-filled by the name of the pack directory inside the archive file (if such a directory exists).

### `author`

The author(s) of the pack.

### `release_date`

The release date of the pack. Possible formats include:

- `YYYY-MM-DD`
- `YYYY-MM-DD HH:MM:SS` (time assumed to be in the server's time zone as specified by `settings.TIME_ZONE`)
- `YYYY` (for packs with a known release year but an unknown date; only the release year will display in the frontend)

### `category`

The pack category (Stream, Technical, etc.). If the pack category doesn't exist yet, a new one will be created automatically upon upload.

### `tags`

A comma-separated list of tags. If a tag doesn't exist yet, it will be created automatically upon upload.

### `source_link`

A URL where ITGdb can fetch the pack from. **This value must not be blank.**

There is some special handing for certain URLs that allow ITGdb to download from them even if they are not direct links; these special cases are detailed below. Otherwise, the URL should be a direct link to a pack archive file (e.g. a .zip).

- Google Drive file link (`https://drive.google.com/...`): ITGdb will use `gdown` (with fuzzy file ID extraction) to retrieve the file.
- Google Drive folder link (`https://drive.google.com/drive/folders/...`): ITGdb will use `gdown` to retrieve the folder. Note that this is prone to running into problems if the folder is large/has lots of items.
- Dropbox (`https://www.dropbox.com/...`): ITGdb can obtain a direct download link by changing the `dl=0` query parameter to `dl=1`.
- Stepmania Online pack page (`https://stepmaniaonline.net/pack/...`): ITGdb can obtain a direct download link from the pack page.
- ~~MEGA file link (`https://mega.nz/...`): ITGdb will use `mega.py` to retrieve the file.~~ This seems to be broken right now.

Note that `file://` URLs also work, if the packs are being stored locally for some reason.

**Special case**: You can also specify this value to be the exact string `(see below)`. In this case, the source URL used will instead be the one specified in the row below. This is useful if an archive file contains multiple pack directories that you want to upload, since ITGdb can just download this file one time instead of once for each pack. You are also allowed to chain multiple `(see below)`s in a row to upload 3+ packs from one archive file.

### `label1`, `link1`, `label2`, `link2`, ...

The remaining values specify the download/information links displayed on ITGdb's pack pages. These values should alternate between the link text (e.g. "Download" or "Information") and the link URL. You may add as many links as you want. After uploading, the blank values are filtered out, and the remaining non-blank values are grouped into (label, URL) pairs.

**Special case:** if the `label1` value is blank (thus leading to an odd number of non-blank values), the link text is auto-filled in as "Download". This allows you to just specify `link1` in the CSV to create a complete download link.