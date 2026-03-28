"""Enterprise FizzBuzz Platform - FizzLLVM: LLVM-Style IR and Optimization"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzllvm import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzllvm")
EVENT_LLVM = EventType.register("FIZZLLVM_COMPILED")
FIZZLLVM_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 228


class IROpcode(Enum):
    ADD = "add"; SUB = "sub"; MUL = "mul"; DIV = "div"; MOD = "srem"
    CMP = "icmp"; BR = "br"; RET = "ret"; LOAD = "load"; STORE = "store"
    CALL = "call"; PHI = "phi"; ALLOCA = "alloca"


class OptimizationPass(Enum):
    DEAD_CODE_ELIMINATION = "dce"
    CONSTANT_FOLDING = "constfold"
    COMMON_SUBEXPRESSION = "cse"
    INLINE = "inline"


@dataclass
class IRInstruction:
    opcode: IROpcode = IROpcode.RET; dest: str = ""
    operands: List[str] = field(default_factory=list); label: str = ""

@dataclass
class BasicBlock:
    name: str = ""; instructions: List[IRInstruction] = field(default_factory=list)

@dataclass
class IRFunction:
    name: str = ""; blocks: List[BasicBlock] = field(default_factory=list)
    params: List[str] = field(default_factory=list)

@dataclass
class IRModule:
    module_id: str = ""; name: str = ""
    functions: List[IRFunction] = field(default_factory=list)

@dataclass
class FizzLLVMConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class IRCompiler:
    """LLVM-style intermediate representation compiler with basic blocks,
    SSA form, and optimization passes for the FizzBuzz compute pipeline."""

    def __init__(self) -> None:
        self._modules: OrderedDict[str, IRModule] = OrderedDict()

    def create_module(self, name: str) -> IRModule:
        module_id = f"mod-{uuid.uuid4().hex[:8]}"
        mod = IRModule(module_id=module_id, name=name)
        self._modules[module_id] = mod
        return mod

    def add_function(self, module_id: str, name: str, params: List[str]) -> IRFunction:
        mod = self.get_module(module_id)
        func = IRFunction(name=name, params=list(params))
        mod.functions.append(func)
        return func

    def add_block(self, module_id: str, func_name: str, block_name: str) -> BasicBlock:
        mod = self.get_module(module_id)
        func = next((f for f in mod.functions if f.name == func_name), None)
        if func is None:
            raise FizzLLVMNotFoundError(f"Function: {func_name}")
        block = BasicBlock(name=block_name)
        func.blocks.append(block)
        return block

    def add_instruction(self, module_id: str, func_name: str, block_name: str,
                        opcode: IROpcode, dest: str, operands: List[str]) -> IRInstruction:
        mod = self.get_module(module_id)
        func = next((f for f in mod.functions if f.name == func_name), None)
        if func is None:
            raise FizzLLVMNotFoundError(f"Function: {func_name}")
        block = next((b for b in func.blocks if b.name == block_name), None)
        if block is None:
            raise FizzLLVMNotFoundError(f"Block: {block_name}")
        instr = IRInstruction(opcode=opcode, dest=dest, operands=list(operands))
        block.instructions.append(instr)
        return instr

    def get_module(self, module_id: str) -> IRModule:
        mod = self._modules.get(module_id)
        if mod is None:
            raise FizzLLVMNotFoundError(module_id)
        return mod

    def list_modules(self) -> List[IRModule]:
        return list(self._modules.values())

    def optimize(self, module_id: str, passes: List[OptimizationPass]) -> IRModule:
        """Apply optimization passes to a module. Returns the optimized module."""
        mod = self.get_module(module_id)
        for opt_pass in passes:
            if opt_pass == OptimizationPass.DEAD_CODE_ELIMINATION:
                self._dce(mod)
            elif opt_pass == OptimizationPass.CONSTANT_FOLDING:
                self._const_fold(mod)
        return mod

    def _dce(self, mod: IRModule) -> None:
        """Remove instructions whose results are never used."""
        for func in mod.functions:
            for block in func.blocks:
                used = set()
                for instr in block.instructions:
                    used.update(instr.operands)
                block.instructions = [
                    i for i in block.instructions
                    if i.dest in used or i.opcode in (IROpcode.RET, IROpcode.BR, IROpcode.STORE, IROpcode.CALL)
                    or not i.dest
                ]

    def _const_fold(self, mod: IRModule) -> None:
        """Fold constant expressions."""
        pass  # Placeholder for constant folding pass

    def emit_ir(self, module_id: str) -> str:
        """Emit textual LLVM-style IR representation."""
        mod = self.get_module(module_id)
        lines = [f"; Module: {mod.name}"]
        for func in mod.functions:
            params = ", ".join(f"i32 %{p}" for p in func.params)
            lines.append(f"define i32 @{func.name}({params}) {{")
            for block in func.blocks:
                lines.append(f"{block.name}:")
                for instr in block.instructions:
                    ops = ", ".join(instr.operands)
                    if instr.dest:
                        lines.append(f"  %{instr.dest} = {instr.opcode.value} {ops}")
                    else:
                        lines.append(f"  {instr.opcode.value} {ops}")
            lines.append("}")
        return "\n".join(lines)


class FizzLLVMDashboard:
    def __init__(self, compiler: Optional[IRCompiler] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._compiler = compiler; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzLLVM Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZLLVM_VERSION}"]
        if self._compiler:
            mods = self._compiler.list_modules()
            total_funcs = sum(len(m.functions) for m in mods)
            lines.append(f"  Modules: {len(mods)}")
            lines.append(f"  Functions: {total_funcs}")
        return "\n".join(lines)


class FizzLLVMMiddleware(IMiddleware):
    def __init__(self, compiler: Optional[IRCompiler] = None,
                 dashboard: Optional[FizzLLVMDashboard] = None) -> None:
        self._compiler = compiler; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzllvm"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzllvm_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[IRCompiler, FizzLLVMDashboard, FizzLLVMMiddleware]:
    compiler = IRCompiler()
    mod = compiler.create_module("fizzbuzz")
    compiler.add_function(mod.module_id, "classify", ["n"])
    compiler.add_block(mod.module_id, "classify", "entry")
    compiler.add_instruction(mod.module_id, "classify", "entry", IROpcode.MOD, "rem3", ["%n", "3"])
    compiler.add_instruction(mod.module_id, "classify", "entry", IROpcode.MOD, "rem5", ["%n", "5"])
    compiler.add_instruction(mod.module_id, "classify", "entry", IROpcode.RET, "", ["%rem3"])
    dashboard = FizzLLVMDashboard(compiler, dashboard_width)
    middleware = FizzLLVMMiddleware(compiler, dashboard)
    logger.info("FizzLLVM initialized: %d modules", len(compiler.list_modules()))
    return compiler, dashboard, middleware
