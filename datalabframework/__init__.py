import os
import sys
import io
import types
import logging

import nbformat

from IPython.display import HTML

from IPython.core.interactiveshell import InteractiveShell
from IPython.core.magic import (Magics, magics_class, line_magic,
                                cell_magic, line_cell_magic)

#automatically imports submodules
from . import export
from . import log
from . import notebook
from . import params
from . import project

__all__ = ['export', 'log', 'notebook', 'params', 'project']

def detect_filename():
      output = """
        <script type="text/javascript">
        
        var nb = null;
        var kernel = null;

        if (IPython && 
            IPython.notebook && 
            IPython.notebook.kernel &&
            IPython.notebook.kernel.info_reply &&
            IPython.notebook.kernel.info_reply.status &&
            IPython.notebook.kernel.info_reply.status == "ok") {
            nb = IPython.notebook; 
            kernel = IPython.notebook.kernel;
        }
        
        if (nb && kernel) {
            var filename = nb.notebook_path;
            var basename = filename.substring(filename.lastIndexOf('/') + 1);
            var msg = 'Detected filename: '+basename;
            document.getElementById("detected_notebook_filename_tag").innerHTML=msg;
            var command = "import os; os.environ['NB_FILENAME']= '" + basename + "'";
            kernel.execute(command);
        } else {
            var msg = 'Not connected to kernel.';
            document.getElementById("detected_notebook_filename_tag").innerHTML=msg;
        }
        </script><pre id="detected_notebook_filename_tag"></pre>
      """
      return(HTML(output))

def filename():
    # env variable is overwritten by the cell magic datalabframework
    
    # when using nbconvert also consider injecting __NB_ROOTPATH__  
    # and __NB_FILENAME__ as a cell in the dictionary of the notebook

    return os.getenv('NB_FILENAME')


def rootpath(rootfile='main.ipynb', levels=5):
    # start from here and go up
    # till you find a main.ipynb
    global __NB_ROOTPATH__ 

    path = '.'
    while levels>0:
        ls = os.listdir(path)
        if rootfile in ls:
            return os.path.abspath(path)

        # we should still be inside a python (hierarchical) package
        # if not, we have gone too far
        if '__init__.py' not in ls:
            return None

        path += '/..'
        levels -= 1

    return None

@magics_class
class DataLabFramework(Magics):

    @cell_magic
    def datalabframework(self, line, cell):
        "A lean data science framework"
        # keep the magic to the minimum
        # add the detected ipython filename in the framework
        # the magic overwrite the env variable
        return detect_filename()

def load_ipython_extension(ipython):
    # The `ipython` argument is the currently active `InteractiveShell`
    # instance, which can be used in any way. This allows you to register
    # new magics or aliases, for example.
    
    def _run_cell_magic(self, magic_name, line, cell):
        if len(cell) == 0 or cell.isspace():
            fn = self.find_line_magic(magic_name)
            if fn:
                return _orig_run_line_magic(self, magic_name, line)
            # IPython will complain if cell is empty string 
            # but not if it is None
            cell = None
        return _orig_run_cell_magic(self, magic_name, line, cell)


    _orig_run_cell_magic = InteractiveShell.run_cell_magic
    InteractiveShell.run_cell_magic = _run_cell_magic

    # In order to actually use these magics, you must register them with a
    # running IPython.  This code must be placed in a file that is loaded once
    # IPython is up and running:
    ip = get_ipython()
    # You can register the class itself without instantiating it.  IPython will
    # call the default constructor on it.
    ip.register_magics(DataLabFramework)


def unload_ipython_extension(ipython):
    # If you want your extension to be unloadable, put that logic here.
    pass

def find_notebook(fullname, path=None):
    """find a notebook, given its fully qualified name and an optional path
    
    This turns "foo.bar" into "foo/bar.ipynb"
    and tries turning "Foo_Bar" into "Foo Bar" if Foo_Bar
    does not exist.
    """
    name = fullname.rsplit('.', 1)[-1]
    if not path:
        path = ['']
    for d in path:
        nb_path = os.path.join(d, name + ".ipynb")
        if os.path.isfile(nb_path):
            return nb_path
        # let import Notebook_Name find "Notebook Name.ipynb"
        nb_path = nb_path.replace("_", " ")
        if os.path.isfile(nb_path):
            return nb_path

class NotebookLoader(object):
    """Module Loader for Jupyter Notebooks"""
    def __init__(self, path=None):
        self.shell = InteractiveShell.instance()
        self.path = path
    
    def load_module(self, fullname):
        """import a notebook as a module"""
        path = find_notebook(fullname, self.path)
        
        print ("importing Jupyter notebook from %s" % path)
                                       
        # load the notebook object
        with io.open(path, 'r', encoding='utf-8') as f:
            nb = nbformat.read(f, 4)
        
        
        # create the module and add it to sys.modules
        # if name in sys.modules:
        #    return sys.modules[name]
        mod = types.ModuleType(fullname)
        mod.__file__ = path
        mod.__loader__ = self
        mod.__dict__['get_ipython'] = get_ipython
        sys.modules[fullname] = mod
        
        # extra work to ensure that magics that would affect the user_ns
        # actually affect the notebook module's ns
        save_user_ns = self.shell.user_ns
        self.shell.user_ns = mod.__dict__
        
        try:
          for cell in nb.cells:
            if cell['cell_type'] == 'code' and cell['source'].startswith('# EXPORT'):
                # transform the input to executable Python
                code = self.shell.input_transformer_manager.transform_cell(cell.source)

                # run the code in themodule
                exec(code, mod.__dict__)
        finally:
            self.shell.user_ns = save_user_ns
        return mod

class NotebookFinder(object):
    """Module finder that locates Jupyter Notebooks"""
    def __init__(self):
        self.loaders = {}
    
    def find_module(self, fullname, path=None):
        nb_path = find_notebook(fullname, path)
        if not nb_path:
            return
        
        key = path
        if path:
            # lists aren't hashable
            key = os.path.sep.join(path)
        
        if key not in self.loaders:
            self.loaders[key] = NotebookLoader(path)
        return self.loaders[key]


# Add rootpath() if available
if rootpath() and rootpath() not in sys.path: 
    sys.path.append(rootpath())

# register hook for loading ipynb files
sys.meta_path.append(NotebookFinder())

# logging
