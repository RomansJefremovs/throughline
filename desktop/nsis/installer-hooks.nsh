; Installer hooks for the Throughline NSIS installer.
;
; Tauri includes this file near the top of the generated installer.nsi,
; before the template's own includes, so everything it needs has to be
; pulled in here. StrFunc.nsh (and the LogicLib.nsh it pulls in) guard
; against double inclusion, so the template's later include of StrFunc
; is a no-op.
;
; The install directory holds the throughline CLI next to the desktop
; shell. The stock Tauri installer never puts it on PATH, but the skill
; the app hands to the agent runs `throughline` from a shell, so the
; hooks below add the directory to the user PATH on install and remove
; it on uninstall. User scope matches the default per-user install:
; no elevation needed, and nothing is written for other accounts.
;
; The stock NSIS 3.11 that Tauri ships carries no EnvVarUpdate.nsh, so
; the list surgery is done with core commands plus StrFunc's StrStr
; (UnStrStr in the uninstaller hook). ReadRegStr returns the raw value,
; so %VARS% in an existing PATH survive the round trip; WriteRegExpandStr
; keeps them that way.

!include "StrFunc.nsh"
${Using:StrFunc} StrStr
${Using:StrFunc} UnStrStr

; Tell Explorer the environment changed so processes it launches pick
; the new PATH up. Already-open terminals only see it on next launch.
!define TL_BROADCAST 0xFFFF
!define TL_WM_SETTINGCHANGE 0x1A

!macro NSIS_HOOK_POSTINSTALL
  ; StrStr clobbers $R0 and $R1, so the live PATH value stays in $R6.
  ReadRegStr $R6 HKCU "Environment" "Path"

  ; A trailing ';' would leave an empty entry behind. StrCpy's optional
  ; arguments are [maxlen] [start], so 1 -1 reads the last character
  ; and -1 as maxlen drops the final character.
  StrCpy $R1 $R6 1 -1
  StrCmp $R1 ";" tl_strip_trailing tl_keep_trailing
  tl_strip_trailing:
    StrCpy $R6 $R6 -1
  tl_keep_trailing:

  ; Appending ';' to both sides turns the substring test into an exact
  ; entry test: no PATH entry ever contains ';', so "...\Throughline;"
  ; cannot match inside "...\Throughline\subdir".
  StrCpy $R1 "$R6;"
  StrCpy $R2 "$INSTDIR;"
  ${StrStr} $R3 "$R1" "$R2"
  StrCmp $R3 "" tl_path_add tl_path_present
  tl_path_present:
    DetailPrint "the user PATH already contains $INSTDIR"
    Goto tl_path_done

  tl_path_add:
  ${If} $R6 == ""
    StrCpy $R6 "$INSTDIR"
  ${Else}
    StrCpy $R6 "$R6;$INSTDIR"
  ${EndIf}
  WriteRegExpandStr HKCU "Environment" "Path" "$R6"
  System::Call 'kernel32::PostMessageA(i ${TL_BROADCAST}, i ${TL_WM_SETTINGCHANGE}, i 0, t "Environment")'
  DetailPrint "added $INSTDIR to the user PATH"

  tl_path_done:
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; An in-place update runs the old uninstaller with /UPDATE. The
  ; directory is about to be reused, so the entry stays.
  ${If} $UpdateMode = 1
    Return
  ${EndIf}

  ; UnStrStr clobbers $R0 and $R1, so the walk keeps its state in $R6-$R9.
  ReadRegStr $R6 HKCU "Environment" "Path"
  StrCmp $R6 "" tl_uninstall_done

  ; Walk the list and rebuild it without $INSTDIR.
  StrCpy $R7 ""
  tl_walk_entry:
  ${UnStrStr} $R8 "$R6" ";"
  StrCmp $R8 "" tl_walk_tail
  StrLen $R0 $R6
  StrLen $R1 $R8
  IntOp $R1 $R0 - $R1
  StrCpy $R9 $R6 $R1
  StrCmp $R9 "$INSTDIR" tl_walk_skip
  StrCpy $R7 "$R7$R9;"
  tl_walk_skip:
  ; UnStrStr's result includes the ';' itself, so skip past it or the
  ; walk would re-find the same separator and never advance. Empty
  ; maxlen plus start 1 keeps everything after the separator.
  StrCpy $R6 $R8 "" 1
  Goto tl_walk_entry
  tl_walk_tail:
  StrCmp $R6 "" tl_walk_end
  StrCmp $R6 "$INSTDIR" tl_walk_end
  StrCpy $R7 "$R7$R6"
  tl_walk_end:

  StrCpy $R9 $R7 1 -1
  StrCmp $R9 ";" tl_unstrip_trailing tl_unkeep_trailing
  tl_unstrip_trailing:
    StrCpy $R7 $R7 -1
  tl_unkeep_trailing:

  StrCmp $R7 "" tl_uninstall_empty
  WriteRegExpandStr HKCU "Environment" "Path" "$R7"
  System::Call 'kernel32::PostMessageA(i ${TL_BROADCAST}, i ${TL_WM_SETTINGCHANGE}, i 0, t "Environment")'
  DetailPrint "removed $INSTDIR from the user PATH"
  Goto tl_uninstall_done

  tl_uninstall_empty:
  DeleteRegValue HKCU "Environment" "Path"
  System::Call 'kernel32::PostMessageA(i ${TL_BROADCAST}, i ${TL_WM_SETTINGCHANGE}, i 0, t "Environment")'

  tl_uninstall_done:
!macroend
