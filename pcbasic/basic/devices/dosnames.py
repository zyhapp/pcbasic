
import os
import re
import string
import sys
import ntpath

from ..base import error


# allowable characters in DOS file name
# GW-BASIC also allows 0x7F and up, but replaces accented chars with unaccented
# based on CHCP code page, which may differ from display codepage in COUNTRY.SYS
# this is complex and leads to unpredictable results depending on host platform.
ALLOWABLE_CHARS = set(string.ascii_letters + string.digits + b" !#$%&'()-@^_`{}~")


##############################################################################
# DOS name translation

class NameConverter(object):
    """Converter between (bytes) DOS names and (unicode) native filenames."""

    def __init__(self, codepage):
        """Initialise converter."""
        self._codepage = codepage

    def match_filename(self, path, name, defext, isdir, create):
        """Find or create a matching native file name for a given BASIC name."""
        # if the name contains a dot, do not apply the default extension
        # to maintain GW-BASIC compatibility, a trailing single dot matches the name
        # with no dots as well as the name with a single dot.
        # file names with more than one dot are not affected.
        # file spec         attempted matches
        # LongFileName      (1) LongFileName.BAS (2) LONGFILE.BAS
        # LongFileName.bas  (1) LongFileName.bas (2) LONGFILE.BAS
        # LongFileName.     (1) LongFileName. (2) LongFileName (3) LONGFILE
        # LongFileName..    (1) LongFileName.. (2) [does not try LONGFILE.. - not allowable]
        # Long.FileName.    (1) Long.FileName. (2) LONG.FIL
        #
        # don't accept leading or trailing whitespace (internal whitespace should be preserved)
        # note that DosBox removes internal whitespace, but MS-DOS does not
        name_err = error.PATH_NOT_FOUND if isdir else error.FILE_NOT_FOUND
        if name != name.strip():
            raise error.BASICError(name_err)
        if defext and b'.' not in name:
            name += b'.' + defext
        elif name[-1] == b'.' and b'.' not in name[:-1]:
            # ends in single dot; first try with dot
            # but if it doesn't exist, base everything off dotless name
            if istype(path, name, isdir):
                return name
            name = name[:-1]
        # convert from codepage to unicode
        name = self._codepage.str_to_unicode(name, box_protect=False)
        # check if the name exists as-is; should also match Windows short names.
        if istype(path, name, isdir):
            return name
        # try to match dossified names
        trunk, ext = split_dosname(name)
        # enforce allowable characters
        if (set(trunk) | set(ext)) - ALLOWABLE_CHARS:
            raise error.BASICError(error.BAD_FILE_NAME)
        dosname = join_dosname(trunk, ext)
        fullname = _match_dosname(dosname, path, isdir)
        if fullname:
            return fullname
        # not found
        if create:
            # create a new filename
            return dosname
        else:
            raise error.BASICError(name_err)

def _match_dosname(dosname, path, isdir):
    """Find a matching native file name for a given 8.3 ascii DOS name."""
    try:
        dosname = dosname.decode(b'ascii')
    except UnicodeDecodeError:
        # non-ascii characters are not allowable for DOS filenames
        return None
    # check if the dossified name exists as-is
    if istype(path, dosname, isdir):
        return dosname
    # find other case combinations, if present
    # also match training single dot to no dots
    trunk, ext = split_dosname(dosname)
    try:
        all_names = sorted(os.listdir(path))
    except EnvironmentError:
        # report no match if listdir fails
        return None
    for f in all_names:
        if split_dosname(f) == (trunk, ext) and istype(path, f, isdir):
            return f
    return None


##############################################################################
# dos path operations

def join_dosname(trunk, ext, padding=False):
    """Join trunk and extension into (bytes) file name."""
    if ext or not trunk:
        ext = b'.' + ext
    if padding:
        return trunk.ljust(8) + ext.ljust(4)
    else:
        return trunk + ext

##############################################################################


if sys.platform == 'win32':
    def short_name(path, longname):
        """Get bytes Windows short name or fake it."""
        path_and_longname = os.path.join(path, longname)
        try:
            # gets the short name if it exists, keeps long name otherwise
            path_and_name = win32api.GetShortPathName(path_and_longname)
        except Exception:
            # something went wrong - keep long name (happens for swap file)
            # this should be a WindowsError which is an OSError
            # but it often is a pywintypes.error
            path_and_name = path_and_longname
        # last element of path is name
        name = path_and_name.split(os.sep)[-1]
        # if we still have a long name, shorten it now
        return split_dosname(name, mark_shortened=True)
else:
    def short_name(dummy_path, longname):
        """Get bytes Windows short name or fake it."""
        # path is only needed on Windows
        return split_dosname(longname, mark_shortened=True)

def split_dosname(name, mark_shortened=False):
    """Convert unicode name into bytes uppercase 8.3 tuple; apply default extension."""
    # convert to all uppercase, no leading or trailing spaces
    # replace non-ascii characters with question marks
    name = name.encode(b'ascii', errors=b'replace').strip().upper()
    # don't try to split special directory names
    if name == b'.':
        return b'', b''
    elif name == b'..':
        return b'', b'.'
    # take whatever comes after first dot as extension
    # and whatever comes before first dot as trunk
    elements = name.split(b'.', 1)
    if len(elements) == 1:
        trunk, ext = elements[0], ''
    else:
        trunk, ext = elements
    # truncate to 8.3
    strunk, sext = trunk[:8], ext[:3]
    # mark shortened file names with a + sign
    # this is used in FILES
    if mark_shortened:
        if strunk != trunk:
            strunk = strunk[:7] + b'+'
        if sext != ext:
            sext = sext[:2] + b'+'
    return strunk, sext

def istype(path, native_name, isdir):
    """Return whether a file exists and is a directory or regular."""
    name = os.path.join(path, native_name)
    try:
        return os.path.isdir(name) if isdir else os.path.isfile(name)
    except TypeError:
        # happens for name = '\0'
        return False

def match_wildcard(name, mask):
    """Whether filename name matches DOS wildcard mask."""
    # convert wildcard mask to regexp
    regexp = '\A'
    for c in mask:
        if c == '?':
            regexp += '.'
        elif c == '*':
            # we won't need to match newlines, so dot is fine
            regexp += '.*'
        else:
            regexp += re.escape(c)
    regexp += '\Z'
    cregexp = re.compile(regexp)
    return cregexp.match(name) is not None

def filename_from_unicode(name):
    """Replace disallowed characters in filename with ?."""
    name_str = name.encode(b'ascii', b'replace')
    return b''.join(c if c in ALLOWABLE_CHARS | set(b'.') else b'?' for c in name_str)

def filter_names(path, files_list, mask=b'*.*'):
    """Apply filename filter to short version of names."""
    all_files = [short_name(path, name.decode(b'ascii')) for name in files_list]
    # apply mask separately to trunk and extension, dos-style.
    # hide dotfiles
    trunkmask, extmask = split_dosname(mask)
    return sorted([(t, e) for (t, e) in all_files
        if (match_wildcard(t, trunkmask) and match_wildcard(e, extmask) and
            (t or not e or e == b'.'))])
