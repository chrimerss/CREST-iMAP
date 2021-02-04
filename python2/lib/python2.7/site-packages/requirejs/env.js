var console = {
    'history': [],
    'log': function() {
        console.history.push([].map.call(arguments, function(cell) {
            return "" + cell;
        }).join(' '));
    }
};
console.debug = console.info = console.warn = console.error = console.log;

var process = {
    "versions": {"node": true},
    "argv": ['node'],
    "nextTick": function(fn) {
        fn();
    },
    'stdout': {},
    'stderr': {}
};


var _readFiles = {}, _readDirs = {};
function addFile(filename, contents) {
    filename = normalizePath(filename);
    _readFiles[filename] = contents;
    var dirname = _reg.path.dirname(filename);
    while (!_readDirs[dirname]) {
        _readDirs[dirname] = true;
        dirname = _reg.path.dirname(dirname);
    }
}

function setArgV(argv) {
    process.argv = argv;
}

var _basePath = null;
function setBasePath(path) {
    _basePath = path;
}

function normalizePath(filename) {
    return _reg.fs.realpathSync(_reg.path.normalize(filename));
}

_writeFiles = {};
_writeDirs = {};
_deleteFiles = {};
_deleteDirs = {};

var _reg = {
    'fs': {
         'existsSync': function(filename) {
             filename = normalizePath(filename);
             if (_readFiles[filename])
                 return true;
             if (_readDirs[filename] || _readDirs[filename.replace(/\/$/, '')])
                 return true;
             return false;
         },
         'statSync': function(filename) {
             filename = normalizePath(filename);
             var isFile = false, isDirectory = false;
             var stats = {
                 'isFile': function() {
                     return isFile;
                 },
                 'isDirectory': function() {
                     return isDirectory;
                 },
                 'mtime': new Date(0)
             };
             if (_readFiles.hasOwnProperty(filename)) {
                 isFile = true;
                 return stats;
             } else if (_readDirs[filename] || _readDirs[filename.replace(/\/$/, '')]) {
                 isDirectory = true;
                 return stats;
             } else {
                 throw new Error(filename + " not found");
             }
         },
         'lstatSync': function(filename) {
             return this.statSync(filename);
         },
         'realpathSync': function(filename) {
             if (filename == '.') {
                 filename = _basePath;
             } else if (filename.indexOf('./') === 0) {
                 filename = _basePath + filename.slice(1);
             }
             return filename;
         },
         'readFileSync': function(filename) {
             filename = normalizePath(filename);
             if (!_readFiles.hasOwnProperty(filename)) {
                 throw new Error(filename + ' not found.');
             }
             return _readFiles[filename];
         },
         'mkdirSync': function(path) {
             path = normalizePath(path);
             _writeDirs[path] = true;
             _readDirs[path] = true;
         },
         'readdirSync': function(path) {
             path = normalizePath(path);
             var filenames = [];
             if (!path.match(/\/$/)) {
                 path += '/';
             }
             (Object.keys(_readFiles).concat(Object.keys(_readDirs))).forEach(function(filename) {
                 if (filename.indexOf(path) === 0 && filename != path) {
                      filename = filename.replace(path, '');
                      if (filename.indexOf('/') == -1) {
                          filenames.push(filename);
                      }
                 }
             });
             return filenames;
         },
         'writeFileSync': function(path, data) {
             path = normalizePath(path);
             addFile(path, data);
             _writeFiles[path] = data;
         },
         'renameSync': function(oldpath, newpath) {
             oldpath = normalizePath(oldpath);
             newpath = normalizePath(newpath);
             this.writeFileSync(newpath, _writeFiles[oldpath]);
             this.unlinkSync(oldpath);
         },
         'unlinkSync': function(path) {
             path = normalizePath(path);
             _deleteFiles[path] = true;
             delete _writeFiles[path];
             delete _readFiles[path];
         },
         'rmdirSync': function(path) {
             path = normalizePath(path);
             var key;
             for (key in _readFiles) {
                 if (key.indexOf(path + '/') === 0) {
                     this.unlinkSync(key);
                 }
             }
             for (key in _readDirs) {
                 if (key == path || key.indexOf(path + '/') === 0) {
                     _deleteDirs[path] = true;
                     delete _readDirs[path];
                     delete _writeDirs[path];
                 }
             }
         }
    },
    'path': {
         'normalize': function(filename) {
             filename = filename.replace(/\/[^\.\/]+\/\.\.\//g, "/")
                 .replace(/\/\.\//g, "/")
                 .replace(/\/.$/, "/");
             return filename;
         },
         'resolve': function(filename) {
             return filename;
         },
         'dirname': function(filename) {
             if (filename == '/') {
                 return filename;
             }
             var parts = filename.split('/');
             var dir = parts.slice(0, -2).join('/');
             if (parts[parts.length - 1]) {
                 dir += '/' + parts[parts.length - 2];
             }
             return dir || '.';
         },
         'join': function() {
             return [].slice.call(arguments).join('/').replace('\/\/', '\/');
         }
    },
    'vm': {
        'runInThisContext': function(str, name) {
            /* jshint evil: true */
            eval(str);
        }
    }
};

function require(name) {
    return _reg[name] || {};
}
var module = {};

var lastCallback = function() {};
function wrapCallback(name) {
    lastCallback = function(arg) {
         var result = null;
         module.exports[name](arg, function(res) {
             result = res;
         });
         return result;
    };
}
