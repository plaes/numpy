import os, sys
import string, re

import build_tools

import base_spec
import scalar_spec
import sequence_spec
import common_spec

default_type_factories = [scalar_spec.int_specification(),
                          scalar_spec.float_specification(),
                          scalar_spec.complex_specification(),
                          sequence_spec.string_specification(),
                          sequence_spec.list_specification(),
                          sequence_spec.dict_specification(),
                          sequence_spec.tuple_specification(),
                          common_spec.file_specification(),
                          common_spec.callable_specification()]
                          #common_spec.instance_specification(),                          
                          #common_spec.module_specification()]

try: 
    from standard_array_spec import array_specification
    default_type_factories.append(array_specification())
except: 
    pass    

try: 
    # this is currently safe because it doesn't import wxPython.
    import wx_spec
    default_type_factories.append(wx_spec.wx_specification())
except: 
    pass    

class ext_function_from_specs:
    def __init__(self,name,code_block,arg_specs):
        self.name = name
        self.arg_specs = base_spec.arg_spec_list(arg_specs)
        self.code_block = code_block
        self.compiler = ''
        self.customize = base_info.custom_info()
        
    def header_code(self):
        pass

    def function_declaration_code(self):
       code  = 'static PyObject* %s(PyObject*self, PyObject* args,' \
               ' PyObject* kywds)\n{\n'
       return code % self.name

    def template_declaration_code(self):
        code = 'template<class T>\n' \
               'static PyObject* %s(PyObject*self, PyObject* args,' \
               ' PyObject* kywds)\n{\n'
        return code % self.name

    #def cpp_function_declaration_code(self):
    #    pass
    #def cpp_function_call_code(self):
    #s    pass
        
    def parse_tuple_code(self):
        """ Create code block for PyArg_ParseTuple.  Variable declarations
            for all PyObjects are done also.
            
            This code got a lot uglier when I added local_dict...
        """
        join = string.join

        declare_return = 'PyObject *return_val = NULL;\n' \
                         'int exception_occured = 0;\n' \
                         'PyObject *py_local_dict = NULL;\n'
        arg_string_list = self.arg_specs.variable_as_strings() + ['"local_dict"']
        arg_strings = join(arg_string_list,',')
        if arg_strings: arg_strings += ','
        declare_kwlist = 'static char *kwlist[] = {%s NULL};\n' % arg_strings

        py_objects = join(self.arg_specs.py_pointers(),', ')
        if py_objects:
            declare_py_objects = 'PyObject ' + py_objects +';\n'
        else:
            declare_py_objects = ''
            
        py_vars = join(self.arg_specs.py_variables(),' = ')
        if py_vars:
            init_values = py_vars + ' = NULL;\n\n'
        else:
            init_values = ''    

        #Each variable is in charge of its own cleanup now.
        #cnt = len(arg_list)
        #declare_cleanup = "blitz::TinyVector<PyObject*,%d> clean_up(0);\n" % cnt

        ref_string = join(self.arg_specs.py_references(),', ')
        if ref_string:
            ref_string += ', &py_local_dict'
        else:
            ref_string = '&py_local_dict'
            
        format = "O"* len(self.arg_specs) + "|O" + ':' + self.name
        parse_tuple =  'if(!PyArg_ParseTupleAndKeywords(args,' \
                             'kywds,"%s",kwlist,%s))\n' % (format,ref_string)
        parse_tuple += '   return NULL;\n'

        return   declare_return + declare_kwlist + declare_py_objects  \
               + init_values + parse_tuple

    def arg_declaration_code(self):
        arg_strings = []
        for arg in self.arg_specs:
            arg_strings.append(arg.declaration_code())
        code = string.join(arg_strings,"")
        return code

    def arg_cleanup_code(self):
        arg_strings = []
        for arg in self.arg_specs:
            arg_strings.append(arg.cleanup_code())
        code = string.join(arg_strings,"")
        return code

    def arg_local_dict_code(self):
        arg_strings = []
        for arg in self.arg_specs:
            arg_strings.append(arg.local_dict_code())
        code = string.join(arg_strings,"")
        return code
        
    def function_code(self):
        decl_code = indent(self.arg_declaration_code(),4)
        cleanup_code = indent(self.arg_cleanup_code(),4)
        function_code = indent(self.code_block,4)
        local_dict_code = indent(self.arg_local_dict_code(),4)

        dict_code = "if(py_local_dict)                                  \n"   \
                    "{                                                  \n"   \
                    "    Py::Dict local_dict = Py::Dict(py_local_dict); \n" + \
                         local_dict_code                                    + \
                    "}                                                  \n"

        try_code =    "try                              \n"   \
                      "{                                \n" + \
                           decl_code                        + \
                      "    /*<function call here>*/     \n" + \
                           function_code                    + \
                           indent(dict_code,4)              + \
                      "\n}                                \n"
        catch_code =  "catch( Py::Exception& e)           \n"   \
                      "{                                \n" + \
                      "    return_val =  Py::Null();    \n"   \
                      "    exception_occured = 1;       \n"   \
                      "}                                \n"

        return_code = "    /*cleanup code*/                     \n" + \
                           cleanup_code                             + \
                      "    if(!return_val && !exception_occured)\n"   \
                      "    {\n                                  \n"   \
                      "        Py_INCREF(Py_None);              \n"   \
                      "        return_val = Py_None;            \n"   \
                      "    }\n                                  \n"   \
                      "    return return_val;           \n"           \
                      "}                                \n"

        all_code = self.function_declaration_code()         + \
                       indent(self.parse_tuple_code(),4)    + \
                       indent(try_code,4)                   + \
                       indent(catch_code,4)                 + \
                       return_code

        return all_code

    def python_function_definition_code(self):
        args = (self.name, self.name)
        function_decls = '{"%s",(PyCFunction)%s , METH_VARARGS|' \
                          'METH_KEYWORDS},\n' % args
        return function_decls

    def set_compiler(self,compiler):
        self.compiler = compiler
        for arg in self.arg_specs:
            arg.set_compiler(compiler)


class ext_function(ext_function_from_specs):
    def __init__(self,name,code_block, args, local_dict=None, global_dict=None,
                 auto_downcast=1, type_factories=None):
                    
        call_frame = sys._getframe().f_back
        if local_dict is None:
            local_dict = call_frame.f_locals
        if global_dict is None:
            global_dict = call_frame.f_globals
        if type_factories is None:
            type_factories = default_type_factories
        arg_specs = assign_variable_types(args,local_dict, global_dict,
                                          auto_downcast, type_factories)
        ext_function_from_specs.__init__(self,name,code_block,arg_specs)
        
            
import base_info, common_info, cxx_info, scalar_info

class ext_module:
    def __init__(self,name,compiler=''):
        standard_info = [common_info.basic_module_info(),
                         common_info.file_info(),  
                         common_info.instance_info(),  
                         common_info.callable_info(),  
                         common_info.module_info(),  
                         cxx_info.cxx_info(),
                         scalar_info.scalar_info()]
        self.name = name
        self.functions = []
        self.compiler = compiler
        self.customize = base_info.custom_info()
        self._build_information = base_info.info_list(standard_info)
        
    def add_function(self,func):
        self.functions.append(func)
    def module_code(self):
        code = self.warning_code() + \
               self.header_code()  + \
               self.support_code() + \
               self.function_code() + \
               self.python_function_definition_code() + \
               self.module_init_code()
        return code

    def arg_specs(self):
        all_arg_specs = base_spec.arg_spec_list()
        for func in self.functions:
            all_arg_specs += func.arg_specs
        return all_arg_specs

    def build_information(self):
        info = [self.customize] + self._build_information + \
               self.arg_specs().build_information()
        for func in self.functions:
            info.append(func.customize)
        #redundant, but easiest place to make sure compiler is set
        for i in info:
            i.set_compiler(self.compiler)
        return info
        
    def get_headers(self):
        all_headers = self.build_information().headers()

        # blitz/array.h always needs to be first so we hack that here...
        if '"blitz/array.h"' in all_headers:
            all_headers.remove('"blitz/array.h"')
            all_headers.insert(0,'"blitz/array.h"')
        return all_headers

    def warning_code(self):
        all_warnings = self.build_information().warnings()
        w=map(lambda x: "#pragma warning(%s)\n" % x,all_warnings)
        return ''.join(w)
        
    def header_code(self):
        h = self.get_headers()
        h= map(lambda x: '#include ' + x + '\n',h)
        return ''.join(h)

    def support_code(self):
        code = self.build_information().support_code()
        return ''.join(code)

    def function_code(self):
        all_function_code = ""
        for func in self.functions:
            all_function_code += func.function_code()
        return ''.join(all_function_code)

    def python_function_definition_code(self):
        all_definition_code = ""
        for func in self.functions:
            all_definition_code += func.python_function_definition_code()
        all_definition_code =  indent(''.join(all_definition_code),4)
        code = 'static PyMethodDef compiled_methods[] = \n' \
               '{\n' \
               '%s' \
               '    {NULL,      NULL}        /* Sentinel */\n' \
               '};\n'
        return code % (all_definition_code)

    def module_init_code(self):
        init_code_list =  self.build_information().module_init_code()
        init_code = indent(''.join(init_code_list),4)
        code = 'extern "C" void init%s()\n' \
               '{\n' \
               '%s' \
               '    (void) Py_InitModule("%s", compiled_methods);\n' \
               '}\n' % (self.name,init_code,self.name)
        return code

    def generate_file(self,file_name="",location='.'):
        code = self.module_code()
        if not file_name:
            file_name = self.name + '.cpp'
        name = generate_file_name(file_name,location)
        #return name
        return generate_module(code,name)

    def set_compiler(self,compiler):
        #for i in self.arg_specs()
        #    i.set_compiler(compiler)
        for i in self.build_information():
            i.set_compiler(compiler)    
        for i in self.functions:
            i.set_compiler(compiler)
        self.compiler = compiler    
        
    def compile(self,location='.',compiler=None, verbose = 0, **kw):
        
        if compiler is not None:
            self.compiler = compiler
        # hmm.  Is there a cleaner way to do this?  Seems like
        # choosing the compiler spagettis around a little.
        compiler = build_tools.choose_compiler(self.compiler)    
        self.set_compiler(compiler)
        arg_specs = self.arg_specs()
        info = self.build_information()
        _source_files = info.sources()
        # remove duplicates
        source_files = {}
        for i in _source_files:
            source_files[i] = None
        source_files = source_files.keys()
        
        # add internally specified macros, includes, etc. to the key words
        # values of the same names so that distutils will use them.
        kw['define_macros'] = kw.get('define_macros',[]) + info.define_macros()
        kw['include_dirs'] = kw.get('include_dirs',[]) + info.include_dirs()
        kw['libraries'] = kw.get('libraries',[]) + info.libraries()
        kw['library_dirs'] = kw.get('library_dirs',[]) + info.library_dirs()
        
        file = self.generate_file(location=location)
        # This is needed so that files build correctly even when different
        # versions of Python are running around.
        import catalog 
        #temp = catalog.default_temp_dir()
        # for speed, build in the machines temp directory
        temp = catalog.intermediate_dir()
        success = build_tools.build_extension(file, temp_dir = temp,
                                              sources = source_files,                                              
                                              compiler_name = compiler,
                                              verbose = verbose, **kw)
        if not success:
            raise SystemError, 'Compilation failed'

def generate_file_name(module_name,module_location):
    module_file = os.path.join(module_location,module_name)
    return os.path.abspath(module_file)

def generate_module(module_string, module_file):
    f =open(module_file,'w')
    f.write(module_string)
    f.close()
    return module_file

def assign_variable_types(variables,local_dict = {}, global_dict = {},
                          auto_downcast = 1,
                          type_factories = default_type_factories):
    incoming_vars = {}
    incoming_vars.update(global_dict)
    incoming_vars.update(local_dict)
    variable_specs = []
    errors={}
    for var in variables:
        try:
            example_type = incoming_vars[var]

            # look through possible type specs to find which one
            # should be used to for example_type
            spec = None
            for factory in type_factories:
                if factory.type_match(example_type):
                    spec = factory.type_spec(var,example_type)
                    break
            if not spec:
                # should really define our own type.
                raise IndexError
            else:
                variable_specs.append(spec)
        except KeyError:
            errors[var] = ("The type and dimensionality specifications" +
                           "for variable '" + var + "' are missing.")
        except IndexError:
            errors[var] = ("Unable to convert variable '"+ var +
                           "' to a C++ type.")
    if errors:
        raise TypeError, format_error_msg(errors)

    if auto_downcast:
        variable_specs = downcast(variable_specs)
    return variable_specs

def downcast(var_specs):
    """ Cast python scalars down to most common type of
         arrays used.

         Right now, focus on complex and float types. Ignore int types.
         Require all arrays to have same type before forcing downcasts.

         Note: var_specs are currently altered in place (horrors...!)
    """
    numeric_types = []

    #grab all the numeric types associated with a variables.
    for var in var_specs:
        if hasattr(var,'numeric_type'):
            numeric_types.append(var.numeric_type)

    # if arrays are present, but none of them are double precision,
    # make all numeric types float or complex(float)
    if (    ('f' in numeric_types or 'F' in numeric_types) and
        not ('d' in numeric_types or 'D' in numeric_types) ):
        for var in var_specs:
            if hasattr(var,'numeric_type'):
                # really should do this some other way...
                if var.numeric_type == type(1+1j):
                    var.numeric_type = 'F'
                elif var.numeric_type == type(1.):
                    var.numeric_type = 'f'
    return var_specs

def indent(st,spaces):
    indention = ' '*spaces
    indented = indention + string.replace(st,'\n','\n'+indention)
    # trim off any trailing spaces
    indented = re.sub(r' +$',r'',indented)
    return indented

def format_error_msg(errors):
    #minimum effort right now...
    import pprint,cStringIO
    msg = cStringIO.StringIO()
    pprint.pprint(errors,msg)
    return msg.getvalue()

def test():
    from scipy_test import module_test
    module_test(__name__,__file__)

def test_suite():
    from scipy_test import module_test_suite
    return module_test_suite(__name__,__file__)    
