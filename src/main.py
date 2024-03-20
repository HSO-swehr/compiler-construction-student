import argparse
from typing import *
import common.genericCompiler as genericCompiler
import common.genericInterp as genericInterp
import common.genericParser as genericParser
import common.utils as utils
import common.log as log
import common.constants as constants
import parsers.lang_simple.simple_parser as simple_parser
import importlib
import shell
import sys
import os
import typing

DEFAULT_OUTPUT = 'out.wasm'

def parseArgs():
    parser = argparse.ArgumentParser(description=f'Run the compiler or interpreter for some language')
    parser.add_argument('--lang', choices=['simple', 'var', 'loop', 'array', 'fun'],
                        help='The language (guessed from path of input file if not given)')
    parser.add_argument('--level', help='The loglevel (debug, info, warn)')
    subparsers = parser.add_subparsers(help='Commands', dest='cmd')

    helpCompiler = f'''Compiles the given input file. Depending on the extension of the output file,
the format is textual or binary.

Exit code {constants.COMPILE_ERROR_EXIT_CODE} for compile error (source program is faulty), all other
exit codes signal a bug in the compiler itself.'''
    cp = subparsers.add_parser('compile', help=helpCompiler)
    def addCompilerArgs(p: argparse.ArgumentParser):
        p.add_argument('--wat2wasm', default='wat2wasm',
                           help='Path to the wat2wasm tool')
        p.add_argument('--output', default=DEFAULT_OUTPUT,
                       help=f'Output file (.wat or .wasm). Default: {DEFAULT_OUTPUT}')
        p.add_argument('--max-mem-size', type=int,
                       help="Max memory size in number of 64kB pages")
        p.add_argument('--max-array-size', type=int,
                       help="Max size of an array in bytes")
        p.add_argument('input', help='Input file .py')
    addCompilerArgs(cp)
    run = subparsers.add_parser('run', help='Compiles the given program and runs it with iwasm. Also see the ' \
        'compile command for help')
    run.add_argument('--run-wasm', default='wasm-support/run_iwasm',
                     help=f'Command to run wasm files')
    addCompilerArgs(run)

    interp = subparsers.add_parser('interp', help='Runs the given file through our own interpeter')
    interp.add_argument('--level', help='The loglevel (debug, info, warn)')
    interp.add_argument('input', help='Input file .py')

    tacInterp = subparsers.add_parser('tacInterp',
                                      help='Compiles the given file to wasm, generates TAC, and ' \
                                        'interpretes the TAC (only works for lang_var and lang_loop)')
    tacInterp.add_argument('--level', help='The loglevel (debug, info, warn)')
    tacInterp.add_argument('input', help='Input file .py')
    tacInterp.add_argument('--wat2wasm', default='wat2wasm', help='Path to the wat2wasm tool')
    tacInterp.add_argument('--print-tac', action='store_true',
                           help='Print the three-address code instructions')

    pyrun = subparsers.add_parser('pyrun',
                                  help='Runs the given file through the python interpreter')
    pyrun.add_argument('input', help='Input file .py')

    p = subparsers.add_parser('parse', help='Parse the given file')
    p.add_argument('--level', help='The loglevel (debug, info, warn)')
    p.add_argument('--alg', choices=['earley', 'lalr'], default='lalr',
                   help='Parsing algorithm (default: lalr)')
    p.add_argument('--grammar', type=str, metavar='FILE',
                   help='Optional .lark grammar')
    p.add_argument('--png', type=str, metavar='FILE',
                   help='Optional .png for for parse tree visualization')
    p.add_argument('input', help='Input file .py')

    args = parser.parse_args()
    if args.cmd is None:
        utils.abort(f'No command given')
    if args.lang == 'simple' and args.cmd != 'parse':
        utils.abort('Language simple only available when parsing')
    return args

def importModule(lang: str, kind: Literal['compile', 'interp', 'ast', 'parse']):
    if lang == 'simple':
        return None
    match kind:
        case "compile":
            modName = f'lang_{lang}.{lang}_compiler'
        case "parse":
            modName = f'parsers.lang_{lang}.{lang}_parser'
        case "interp":
            modName = f'lang_{lang}.{lang}_interp'
        case "ast":
            modName = f'lang_{lang}.{lang}_ast'
    m = importlib.import_module(modName)
    return m

def getFun(mod: Any, fun: str):
    try:
        return getattr(mod, fun)
    except AttributeError:
        utils.abort(f'Module {mod} does not define function {fun}')

def runWasm(runWasmCmd: str, file: str):
    delim = 80 * '-'
    print(delim)
    print(f'Running wasm file {file}')
    print(delim)
    res = shell.run([runWasmCmd, file], onError='ignore')
    ecode = 0 if res.exitcode == 0 else constants.RUN_ERROR_EXIT_CODE
    print(delim)
    print(f'Finished running wasm file {file}, exit code: {ecode}')
    sys.exit(ecode)

PRELUDE_DICT = {
    'input_int': lambda: utils.inputInt('Input some int: '),
    'Callable': cast(Any, typing.Callable)
}

def runWithPython(srcFile: str):
    src = utils.readTextFile(srcFile)
    exec(src, PRELUDE_DICT)

def main():
    args = parseArgs()
    level = log.resolveLevelName(args.level or 'warn')
    log.init(level, 'minipy.log')
    if args.lang:
        lang = args.lang
    else:
        lang = None
        for x in args.input.split(os.sep):
            if x.startswith('lang_'):
                lang = x[len('lang_'):]
        if lang is None:
            utils.abort(f'Language not given with --lang and input file does not allow guessing '\
                'the language.')
    ast = importModule(lang, 'ast')
    match args.cmd:
        case "compile" | "run":
            if args.cmd == "run" and not args.output.endswith('.wasm'):
                utils.abort("For mode=run, output file must be a .wasm file")
            compilerMod = importModule(lang, 'compile')
            compileFun = getFun(compilerMod, 'compileModule')
            compileArgs = genericCompiler.Args(args.input, args.output, args.wat2wasm,
                                                args.max_mem_size, args.max_array_size)
            genericCompiler.compileMain(compileArgs, compileFun, ast)
            if args.cmd == "run":
                runWasm(args.run_wasm, args.output)
        case "interp":
            interpMod = importModule(lang, 'interp')
            interpFun = getFun(interpMod, 'interpModule')
            interpArgs = genericInterp.Args(args.input)
            genericInterp.interpMain(interpArgs, interpFun, ast)
        case "pyrun":
            runWithPython(args.input)
        case "parse":
            parserArgs = genericParser.ParserArgs(utils.readTextFile(args.input),
                                                  args.alg, args.png, args.grammar)
            if lang == 'simple':
                simple_parser.parse(parserArgs)
            else:
                parseMod = importModule(lang, 'parse')
                parseFun = getFun(parseMod, 'parseModule')
                genericParser.parseWithOwnParser(args.input, parserArgs, ast, parseFun)
        case "tacInterp":
            compileArgs = genericCompiler.Args(args.input, '/tmp/dummy.wasm', args.wat2wasm, 1, 1)
            tac_interp = utils.importModuleNotInStudent('compilers.assembly.tac_interp')
            tac_interp.interpFile(compileArgs, args.print_tac)
        case _:
            utils.abort(f'Unknown command: {args.cmd}')

if __name__ == '__main__':
    main()
