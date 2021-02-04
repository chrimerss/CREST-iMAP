# -*- coding: utf-8 -*-
"""
gis.py
~~~~~~~~~~~~~~~~~

Minimal vector, raster and map serving over HTTP2

"""
import argparse
import mimetypes
import posixpath
import urllib
import sys
import glob
import os
import shutil
from http.server import BaseHTTPRequestHandler, HTTPServer, HTTPStatus

__version__ = "0.1"


class GISHTTPRequestHandler(BaseHTTPRequestHandler):

    """Simple HTTP request handler with GET and HEAD commands.

    It looks for an openapi.yaml file instead of index.html

    This serves files from the current directory and any of its
    subdirectories.  The MIME type for files is determined by
    calling the .guess_type() method.

    The GET and HEAD requests are identical except that the HEAD
    request omits the actual contents of the file.

    """

    server_version = "gis/" + __version__

    def do_GET(self):
        """Serve a GET request."""
        f = self.send_head()
        if f:
            try:
                self.copyfile(f, self.wfile)
            finally:
                f.close()

    def do_HEAD(self):
        """Serve a HEAD request."""
        f = self.send_head()
        if f:
            f.close()

    def send_head(self):
        """Common code for GET and HEAD commands.

        This sends the response code and MIME headers.

        Return value is either a file object (which has to be copied
        to the outputfile by the caller unless the command was HEAD,
        and must be closed by the caller under all circumstances), or
        None, in which case the caller has nothing further to do.

        """
        path = self.translate_path(self.path)
        f = None
        if os.path.isdir(path):
            parts = urllib.parse.urlsplit(self.path)
            if not parts.path.endswith('/'):
                # redirect browser - doing basically what apache does
                self.send_response(HTTPStatus.MOVED_PERMANENTLY)
                new_parts = (parts[0], parts[1], parts[2] + '/',
                             parts[3], parts[4])
                new_url = urllib.parse.urlunsplit(new_parts)
                self.send_header("Location", new_url)
                self.end_headers()
                return None
            # If there is only one file, return it.
            try:
                file_list = os.listdir(path)
            except OSError:
                self.send_error(
                    HTTPStatus.NOT_FOUND,
                    "No permission to list directory")

            # If there is more than one file, return
            # the one called openapi.yaml
            if len(file_list) == 1:
                path = os.path.join(path, file_list[0])
            elif len(file_list) > 1:
                for index in "openapi.yml", "openapi.yaml":
                    index = os.path.join(path, index)
                    if os.path.exists(index):
                        path = index
                        break
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "File not found")
        ctype = self.guess_type(path)
        try:
            f = open(path, 'rb')
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-type", ctype)
            fs = os.fstat(f.fileno())
            self.send_header("Content-Length", str(fs[6]))
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()
            return f
        except Exception:
            f.close()
            raise

    def translate_path(self, path):
        """Translate a /-separated PATH to the local filename syntax.

        Components that mean special things to the local file system
        (e.g. drive or directory names) are ignored.  (XXX They should
        probably be diagnosed.)

        """
        # abandon query parameters
        path = path.split('?', 1)[0]
        path = path.split('#', 1)[0]
        # Don't forget explicit trailing slash when normalizing. Issue17324
        trailing_slash = path.rstrip().endswith('/')
        try:
            path = urllib.parse.unquote(path, errors='surrogatepass')
        except UnicodeDecodeError:
            path = urllib.parse.unquote(path)
        path = posixpath.normpath(path)
        words = path.split('/')
        words = filter(None, words)
        path = os.getcwd()
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                # Ignore components that are not a simple file/directory name
                continue
            path = os.path.join(path, word)
        if trailing_slash:
            path += '/'
        return path

    def copyfile(self, source, outputfile):
        """Copy all data between two file objects.

        The SOURCE argument is a file object open for reading
        (or anything with a read() method) and the DESTINATION
        argument is a file object open for writing (or
        anything with a write() method).

        The only reason for overriding this would be to change
        the block size or perhaps to replace newlines by CRLF
        -- note however that this the default server uses this
        to copy binary data as well.

        """
        shutil.copyfileobj(source, outputfile)

    def guess_type(self, path):
        """Guess the type of a file.

        Argument is a PATH (a filename).

        Return value is a string of the form type/subtype,
        usable for a MIME Content-type header.

        The default implementation looks the file's extension
        up in the table self.extensions_map, using application/octet-stream
        as a default; however it would be permissible (if
        slow) to look inside the data to make a better guess.

        """

        base, ext = posixpath.splitext(path)
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        ext = ext.lower()
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        else:
            return self.extensions_map['']

    if not mimetypes.inited:
        mimetypes.init()  # try to read system mime.types
    extensions_map = mimetypes.types_map.copy()
    extensions_map.update({
        '': 'application/octet-stream',  # Default
        '.py': 'text/plain',
        '.c': 'text/plain',
        '.h': 'text/plain',
    })


def index(args):
    """Add data to the index
    """
    import ruido
    directory = args.dir
    vectors = glob.glob(os.path.join(directory, '**', '*.json'), recursive=True)
    rasters = glob.glob(os.path.join(directory, '**', '*.tiff'), recursive=True)
    if args.verbose:
        print("Indexing %s" % directory)
        print("Vectors: %s" % vectors)
        print("Rasters: %s" % rasters)

    for vector in vectors:
        with open(vector, 'r') as v:
            for item_raw in v:
                item = item_raw.strip(u'\u001e')
                ruido.add(os.path.join(".index", vector), item)

    return "[]"


def query(args):
    """Query the existing index
    """
    import ruido
    ruido.query('.index', 'find {} return .')
    return "[]"


def server(args):
    """Runs openapi compatible service to serve the data
    """
    GISHTTPRequestHandler.protocol_version = args.protocol
    httpd = HTTPServer((args.bind, args.port), GISHTTPRequestHandler)

    if args.verbose:
        sa = httpd.socket.getsockname()
        print("Serving GIS on", sa[0], "port", sa[1], "...")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, exiting.")
        httpd.server_close()
        sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Vector, raster and maps')
    subparsers = parser.add_subparsers(help='Command to be run')

    parser_server = subparsers.add_parser('server', help='Run http service')
    parser_server.add_argument('--bind', '-b', default='', metavar='ADDRESS',
                               help='Specify alternate bind address '
                               '[default: all interfaces]')
    parser_server.add_argument('--port', '-p', action='store',
                               default=8443, type=int,
                               nargs='?',
                               help='Specify alternate port [default: 8443]')

    parser_server.add_argument('--protocol', default='HTTP/1.0', metavar='PROTOCOL',
                               help='Specify HTTP protocol'
                               '[default: HTTP/1.0]')
    parser_server.add_argument('--verbose', dest='verbose', action='store_true')
    parser_server.set_defaults(verbose=False)
    parser_server.set_defaults(func=server)

    parser_index = subparsers.add_parser('index', help='Index vector or raster data')
    parser_index.add_argument('--dir', default='.')
    parser_index.add_argument('--verbose', dest='verbose', action='store_true')
    parser_index.set_defaults(verbose=False)
    parser_index.set_defaults(func=index)

    parser_query = subparsers.add_parser('query', help='Query the gis database')
    parser_query.add_argument('-index', default='.catalog')
    parser_query.add_argument('-query', default='find {}')
    parser_query.set_defaults(func=query)

    args = parser.parse_args()

    # Every subcommand defines a func method pointing to the implementation
    # we it is not present we should assume no command was specified and show
    # the general help.
    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit("No command supplied")
    # Invokes the implementation for the command with the arguments defined
    # in the subparser.
    args.func(args)
