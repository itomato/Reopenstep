// Export Ghidra's decompiler output for every function in the current program.
// Usage: -postScript ExportDecompile.java /absolute/or/relative/output.c

import java.io.File;
import java.io.PrintWriter;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

public class ExportDecompile extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("expected output path argument");
        }

        File output = new File(args[0]);
        File parent = output.getAbsoluteFile().getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IllegalStateException("cannot create output directory: " + parent);
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.toggleCCode(true);
        decompiler.toggleSyntaxTree(true);
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("cannot initialize decompiler");
        }

        try (PrintWriter writer = new PrintWriter(output, "UTF-8")) {
            writer.println("/* Ghidra decompiler reference; not buildable source. */");
            writer.println("/* Program: " + currentProgram.getName() + " */");
            FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
            for (Function function : functions) {
                if (monitor.isCancelled()) {
                    break;
                }
                writer.println();
                writer.println("/* " + function.getEntryPoint() + " " + function.getName() + " */");
                DecompileResults results = decompiler.decompileFunction(function, 60, monitor);
                if (results.decompileCompleted() && results.getDecompiledFunction() != null) {
                    writer.println(results.getDecompiledFunction().getC());
                } else {
                    writer.println("/* decompile failed: " + results.getErrorMessage() + " */");
                }
            }
        } finally {
            decompiler.dispose();
        }
        println("Wrote decompiler output to " + output.getAbsolutePath());
    }
}
