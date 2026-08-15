# Elevate-and-install CP210x VCP driver (silabser), then rescan for the ESP32.
$ErrorActionPreference = "Continue"
$log = "D:\SHM_Bridges\tools\esp\driver_install.log"
"=== add-driver ===" | Out-File $log -Encoding utf8
pnputil /add-driver "D:\SHM_Bridges\tools\esp\cp210x_drv\silabser.inf" /install 2>&1 | Out-File $log -Append -Encoding utf8
"=== scan-devices ===" | Out-File $log -Append -Encoding utf8
pnputil /scan-devices 2>&1 | Out-File $log -Append -Encoding utf8
"=== done ===" | Out-File $log -Append -Encoding utf8
