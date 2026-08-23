// Locate the OPENSTEP boot2 installer prompts and print their code references.
// @category ReopenStep

import java.nio.charset.StandardCharsets;

import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class AnalyzeBoot2Prompts extends GhidraScript {
    private Address findPrompt(String text) throws Exception {
        byte[] bytes = (text + "\0").getBytes(StandardCharsets.US_ASCII);
        return currentProgram.getMemory().findBytes(
            currentProgram.getMinAddress(), currentProgram.getMaxAddress(), bytes, null, true, monitor);
    }

    @Override
    public void run() throws Exception {
        // boot1 loads boot2 from disk offset 0x5000 at physical address zero;
        // the boot2 entry at disk offset 0x8000 therefore executes at 0x3000.
        Address entry = toAddr(0x3000);
        disassemble(entry);
        analyzeAll(currentProgram);

        for (String prompt : new String[] {
                "Install Mode", "Language", "Really Install?", "Install Canceled"}) {
            Address address = findPrompt(prompt);
            println(prompt + " @ " + address);
            if (address == null) {
                continue;
            }
            ReferenceIterator references = currentProgram.getReferenceManager().getReferencesTo(address);
            while (references.hasNext()) {
                Reference reference = references.next();
                Instruction instruction = getInstructionAt(reference.getFromAddress());
                println("  " + reference.getFromAddress() + ": " + instruction);
            }
            Address segmentOffset = toAddr(address.getOffset() & 0xffff);
            references = currentProgram.getReferenceManager().getReferencesTo(segmentOffset);
            while (references.hasNext()) {
                Reference reference = references.next();
                Instruction instruction = getInstructionAt(reference.getFromAddress());
                println("  segmented " + reference.getFromAddress() + ": " + instruction);
            }
        }

        println("Instructions containing prompt offsets:");
        InstructionIterator instructions = currentProgram.getListing().getInstructions(true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            String rendered = instruction.toString().toLowerCase();
            if (rendered.contains("0x923") || rendered.contains("0x930") ||
                    rendered.contains("0x939") || rendered.contains("0x949") ||
                    rendered.contains("0923") || rendered.contains("0930") ||
                    rendered.contains("0939") || rendered.contains("0949")) {
                println("  " + instruction.getAddress() + ": " + instruction);
            }
        }
        println("Confirmation pointer neighborhood:");
        for (Address cursor = toAddr(0x3a70); cursor.compareTo(toAddr(0x3b70)) < 0; ) {
            Instruction instruction = getInstructionAt(cursor);
            if (instruction != null) {
                println("  " + cursor + ": " + instruction);
                cursor = instruction.getMaxAddress().next();
            } else {
                cursor = cursor.next();
            }
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        Function promptFunction = getFunctionContaining(toAddr(0x375c));
        if (promptFunction != null) {
            DecompileResults promptResult = decompiler.decompileFunction(promptFunction, 30, monitor);
            if (promptResult.decompileCompleted()) {
                println("Installer prompt function " + promptFunction.getEntryPoint() + ":\n" +
                    promptResult.getDecompiledFunction().getC());
            }
        }
        Function languageFunction = getFunctionContaining(toAddr(0x3b5c));
        if (languageFunction != null) {
            DecompileResults languageResult = decompiler.decompileFunction(languageFunction, 30, monitor);
            if (languageResult.decompileCompleted()) {
                println("Installer language function " + languageFunction.getEntryPoint() + ":\n" +
                    languageResult.getDecompiledFunction().getC());
            }
        }
        decompiler.dispose();
    }
}
