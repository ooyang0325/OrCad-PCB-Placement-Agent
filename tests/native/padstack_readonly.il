; Original opt-in readback check for a bound, all-unplaced managed session.
procedure(opaManagedPadReadOnlyAcceptance(identifier)
    let((before after design pads result output path cases rules)
        opaRequire(opaID(identifier) && !opaDispatchActive "An idle bound session is required.")
        opaBoardGuard()
        opaRequire(opaManagedMode() && !axlDBGetDesign()->symbols
            "Readback is limited to the already-bound all-unplaced managed board.")
        path = opaPath(identifier ".pad-readonly.txt")
        opaRequire(!isFile(path) "Native pad readback report already exists.")
        design = axlDBGetDesign()
        before = opaLibraryPadstacks(design)
        result = errset(
            progn(
                cases = opaManagedThroughPadRulesAcceptance()
                pads = opaManagedPadstacks(design)
                rules = opaManagedConstraints()
                t) t)
        after = opaLibraryPadstacks(design)
        opaRequire(equal(before after) "Native pad definitions changed during readback.")
        output = outfile(path)
        opaRequire(output "Cannot write pad readback report.")
        unwindProtect(
            progn(
                fprintf(output "session %s\nboard %s\n" opaNonce opaBoardPath)
                fprintf(output "success %L\npure_cases %L\n" if(result then t else nil) cases)
                fprintf(output "padstacks %d\n" length(pads))
                fprintf(output "error %s\n" if(result then "" else opaError))
                fprintf(output "constraints %s\n" opaStable(rules))
                fprintf(output "pad_definitions_unchanged t\n")
                fprintf(output "complete %s\n" identifier))
            close(output))
        if(result then t else nil)
    )
)
