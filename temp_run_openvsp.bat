@echo off
REM Set PATH to include OpenVSP's core library and script directories
set "PATH=%PATH%;C:\OpenVSP-3.51.2-win64\python;C:\OpenVSP-3.51.2-win64\scripts"

REM Execute the diagnostic test script using the current PYTHON interpreter setup
python C:\Star\cozy\diag_openvsp_final.py