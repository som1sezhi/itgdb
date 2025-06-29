"""Utility for parsing INI files. I rolled my own instead of using configparser
in order to emulate ITGmania's behavior as closely as possible."""

class IniFile:
    """Holds data from an INI file."""

    def __init__(self, file_path: str):
        """Parses the INI file at `file_path`. Encoding is assumed to be
        UTF-8, which is probably fine?"""
        self.sections: dict[str, dict[str, str]] = {}
        self.raw_text = ''

        with open(file_path, 'r', encoding='utf-8') as file:
            # essentially a port of the logic in IniFile::ReadFile()
            accum_line = ''
            cur_section = None
            for line in file:
                line = line.rstrip('\r\n')
                # backslash indicates a continuation of the line
                if line and line[-1] == '\\':
                    # append the line, minus the backslash
                    accum_line += line[:-1]
                    continue
                # otherwise, the line is terminated
                accum_line += line

                if not accum_line:
                    pass # skip empty line
                elif accum_line.startswith((';', '#', '//', '--')):
                    pass # ignore comments
                elif accum_line[0] == '[' and accum_line[-1] == ']':
                    # new section
                    section_name = accum_line[1:-1]
                    if section_name not in self.sections:
                        self.sections[section_name] = {}
                    cur_section = self.sections[section_name]
                elif cur_section is not None:
                    # new value
                    splits = accum_line.split('=', 1)
                    if len(splits) > 1:
                        val_name = splits[0].strip('\r\n\t ')
                        if val_name:
                            cur_section[val_name] = splits[1]

                # reset
                accum_line = ''

            # NOTE: it is intentional behavior to discard any accum_line
            # left behind when EOF is reached (e.g. through a hanging backslash
            # at the end of the last line)

            file.seek(0)
            self.raw_text = file.read()

    def get(self, section_name: str, value_name: str) -> str | None:
        """Returns the value associated with the given section and value name,
        or None if the section/value name is not present in the file."""
        section = self.sections.get(section_name)
        if section:
            return section.get(value_name)
        return None
    
    def __repr__(self) -> str:
        return f'IniFile({repr(self.sections)})'