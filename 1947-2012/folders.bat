
@echo off
setlocal enabledelayedexpansion

for /L %%Y in (1947,1,2012) do (
    mkdir %%Y
)

echo Folders created from 1947 to 2012.
pause
