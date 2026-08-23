use scripting additions

on waitForWorkbench(processName)
    tell application "System Events"
        repeat 200 times
            if exists process processName then
                tell process processName
                    if exists window 1 then return
                end tell
            end if
            delay 0.1
        end repeat
    end tell
    error "Timed out waiting for ReopenStep Workbench"
end waitForWorkbench

on waitForCommand(processName)
    tell application "System Events"
        tell process processName
            repeat 600 times
                set statusValue to value of static text 1 of window 1
                if statusValue is "Completed" then return
                if statusValue starts with "Failed" then error "Workbench command " & statusValue
                if statusValue is "Launch failed" then error "Workbench command failed to launch"
                delay 0.1
            end repeat
        end tell
    end tell
    error "Timed out waiting for Workbench command"
end waitForCommand

on run arguments
    if (count of arguments) is 0 then error "Repository root argument is required"
    set repositoryRoot to item 1 of arguments

    set processName to "ReopenStepWorkbench"
    set applicationPath to repositoryRoot & "/apps/ReopenStepWorkbench/build/ReopenStepWorkbench.app"
    set payloadPath to repositoryRoot & "/examples/composer-payload"
    set recipePath to repositoryRoot & "/out/composer/WorkbenchFixture.recipe.json"
    set packagePath to repositoryRoot & "/out/composer/WorkbenchFixture.pkg"

    do shell script ("/bin/test -d " & quoted form of applicationPath)
    do shell script ("/bin/test -d " & quoted form of payloadPath)
    do shell script ("/bin/test ! -e " & quoted form of packagePath)

    tell application "System Events"
        if exists process processName then
            tell process processName
                click menu item "Quit ReopenStep Workbench" of menu 1 of menu bar item "ReopenStepWorkbench" of menu bar 1
            end tell
            repeat 200 times
                if not (exists process processName) then exit repeat
                delay 0.1
            end repeat
            if exists process processName then error "Timed out closing the previous Workbench session"
        end if
    end tell
    do shell script ("/usr/bin/open -n " & quoted form of applicationPath)
    my waitForWorkbench(processName)

    tell application "System Events"
        tell process processName
            set frontmost to true
            click radio button "Installation Composer" of tab group 1 of window 1
            tell tab group 1 of window 1
                set value of text field 1 to payloadPath
                set value of text field 2 to "WorkbenchFixture"
                set value of text field 3 to "Workbench Composer Fixture"
                set value of text field 4 to "1.0"
                set value of text field 5 to "Workbench-driven package acceptance fixture"
                set value of text field 6 to "/"
                set value of text field 7 to recipePath
                set value of text field 8 to packagePath
                click button "Create Recipe"
            end tell
        end tell
    end tell
    my waitForCommand(processName)

    tell application "System Events" to tell process processName to tell tab group 1 of window 1
        click button "Build Package"
    end tell
    my waitForCommand(processName)

    tell application "System Events" to tell process processName to tell tab group 1 of window 1
        click button "Inspect Package"
    end tell
    my waitForCommand(processName)

    tell application "System Events" to tell process processName
        return value of text area 1 of scroll area 1 of window 1
    end tell
end run
