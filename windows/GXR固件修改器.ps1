param([string]$Source = "")

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$RepoUrl = "https://github.com/minakam1/ricoh-gxr-chinese-language-patch"

$OfficialHashes = [ordered]@{
    "ilaunch0" = "b896f40d9f330c4235d99bd6e32963876f9701293530a927672fd6fab7281e65"
    "ilaunch3" = "da1980e9d6f3996ede4953b8311cf0ce2abeb4bb300b6ee60a38f38e29a3cdf7"
    "ilaunch4" = "c9271288f8d395296623a3fe5358b2d83dec8730a89ed138a48ff8a2e8f14a5a"
    "ilaunch8" = "071d207858c5863f72fda37274372ab881d86f6ecd2b1a826ad825f90047e478"
    "jlaunch0" = "0606a54c673e6db2b7708598f4ad7f1bebb93ade534087b1d0e28f7aff8e2de9"
    "jlaunch3" = "951be1c659c85af58ae3e4ce98707c52f0b4514fc2075256854d59f822671673"
    "jlaunch4" = "377e980401d98ba303246f00b4633468ef5affa54ffbc22d24659cc4b1c5e8ca"
    "jlaunch8" = "92554edf413e0090550f192973d0555ee13770cee0764802be209f491f2c424f"
    "klaunch0" = "4b8c1fd4c24cc7112d49290e94f8d9d75523df395aec7c8fff7ad6ac881b0bf6"
    "klaunch3" = "491f39a619e7d85eeb28ba5c55494ccaa274872b63b2a98169ee14e8f4757bee"
    "klaunch4" = "2dd87ee852b4cea2aff881da9903871a57910da71b27402b1dd29c8dc77fdfe2"
    "klaunch8" = "8fc3ff589088b90a8922a200a077aa3f9daed1dbb5d37992c0642c0b63f69f1a"
    "l06firm0" = "d7b74b86ec829e90dd4b5c1092abc892b90422fd975942f3d4a6b99ea24e24ef"
    "l06firm3" = "6538b919848ee979c3e92ac14a19a29fb8439a1297147c7e0e601afcd135ae8d"
    "l06firm4" = "c0aa8256c682a41ad96277eea075e2c58dca5335dc9bc824e09e78fe69ab10d0"
    "l06firm5" = "1ddd60028a33aa021169014f07abe263099404522097ad3a267d3fe0387a9c69"
    "l06firm8" = "61aae4cfb39ee599eb9647fb72da7b4fd186edcbda298dcb6551fe1fd78d718d"
    "l08firm0" = "05cc3f648f84dc1123dc8207a0edbd796a70bec9a01c36fa43199a5959b78e9f"
    "l08firm3" = "0a4dff6d3be9b9a9b56dfcbd98a2df59efcb31f7d4eaca6b0c3fbdb1641fde44"
    "l08firm4" = "0f787a6fa51893d98bcc778c9e91b2a46ce4fef139828332f418142aa4f36060"
    "l08firm8" = "59a75b3ea1cb7dc71d79349e20d49e809eb1678731111678a7b0ef4c8df0db4d"
    "nlaunch0" = "480c5b195c983100a80ca3e3128cd2a0686de0f7b482c025ec23db3f8a78f527"
    "nlaunch3" = "f96c5b84b8fb442706dd694828f51bea4f5f38ea11a7c6881d050d479df9aabf"
    "nlaunch4" = "f2bbc71463d9272adc0da8801bc2997a2c147b0ce33c10aaeac01a506e4c678d"
    "nlaunch8" = "52921ca9311de0f093d5dea1531e2c83876f2bf91d7032cf45f60a50328b26be"
    "qlaunch0" = "3bbc37c6c12c6fedaa190927cdc0594d059919cffee29309ef211122734c6dc5"
    "qlaunch3" = "e487d00b5539aa1e3ca9373829456e00676b37310dc717f0a5bcb5235bac6690"
    "qlaunch4" = "eb2533fdb26ee61cc2135c40fa73a2d6f618bd6f1872f594b256ce4b586aa90b"
    "qlaunch8" = "9d81ca7c1e33df4cd9f0c5532b22ad55b1c11a492707839705ab4e69f9019e45"
}

function Convert-Hex([string]$Hex) {
    [byte[]]$result = $Hex.Split(" ", [StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object {
        [Convert]::ToByte($_, 16)
    }
    return ,$result
}

function Get-BE32([byte[]]$Data, [int]$Offset) {
    return [uint32](
        ([uint32]$Data[$Offset] -shl 24) -bor
        ([uint32]$Data[$Offset + 1] -shl 16) -bor
        ([uint32]$Data[$Offset + 2] -shl 8) -bor
        [uint32]$Data[$Offset + 3]
    )
}

function Set-BE32([byte[]]$Data, [int]$Offset, [uint32]$Value) {
    $Data[$Offset] = [byte](($Value -shr 24) -band 0xFF)
    $Data[$Offset + 1] = [byte](($Value -shr 16) -band 0xFF)
    $Data[$Offset + 2] = [byte](($Value -shr 8) -band 0xFF)
    $Data[$Offset + 3] = [byte]($Value -band 0xFF)
}

function Get-FirmwareChecksum([byte[]]$Data) {
    if ((Get-BE32 $Data 0x164) -ne ($Data.Length - 0x200)) {
        throw "ilaunch3 载荷长度不匹配"
    }
    [uint64]$sum = 0
    for ($index = 0; $index -lt $Data.Length - 0x200; $index++) {
        $sum += [uint64]$Data[$index + 0x200] * (($index % 6) + 2)
    }
    return [uint32]($sum % [uint64]4294967296)
}

function Set-ExactPatch([byte[]]$Data, [int]$Offset, [byte[]]$Expected, [byte[]]$Replacement, [string]$Name) {
    if ($Expected.Length -ne $Replacement.Length) { throw "$Name 补丁长度错误" }
    for ($index = 0; $index -lt $Expected.Length; $index++) {
        if ($Data[$Offset + $index] -ne $Expected[$index]) {
            throw "ilaunch3 的 $Name 补丁位置与官方 1.51 不匹配"
        }
    }
    [Array]::Copy($Replacement, 0, $Data, $Offset, $Replacement.Length)
}

function Finish-Patch([byte[]]$Original, [byte[]]$Patched, [string]$ExpectedHash) {
    if ((Get-BE32 $Original 0x16C) -ne (Get-FirmwareChecksum $Original)) {
        throw "官方 ilaunch3 内部校验失败"
    }
    Set-BE32 $Patched 0x16C (Get-FirmwareChecksum $Patched)
    if ((Get-BE32 $Patched 0x16C) -ne (Get-FirmwareChecksum $Patched)) {
        throw "修改后 ilaunch3 内部校验失败"
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $actual = ([BitConverter]::ToString($sha.ComputeHash($Patched))).Replace("-", "").ToLower() }
    finally { $sha.Dispose() }
    if ($actual -ne $ExpectedHash) { throw "修改结果与已验证版本不一致" }
    return ,$Patched
}

function Patch-English([byte[]]$Original) {
    [byte[]]$data = $Original.Clone()
    Set-ExactPatch $data 0x1C348 (Convert-Hex "d0 c0 20 0c 80 e0 0d 9c 20 c0 f0 00 a0 90 00 17") (Convert-Hex "61 01 f0 00 b0 11 00 03 60 06 f0 00 80 e0 00 00") "开机语言配置"
    Set-ExactPatch $data 0x1C774 (Convert-Hex "7f 02") (Convert-Hex "7f 04") "语言同步分支"
    Set-ExactPatch $data 0x1C778 (Convert-Hex "a2 91 00 17 d0 c0 20 0c 80 e0 0d ac 21 c0 f0 00 a2 01 03 97") (Convert-Hex "12 80 61 01 b2 11 00 02 62 06 f0 00 a2 03 03 97 80 e0 00 00") "运行时语言同步"
    Set-ExactPatch $data 0x176150 (Convert-Hex "28 7f 2e 7f 18 84 f0 00 d0 c0 20 1d 80 e0 1e fc 14 88 1e c0 d0 c0 20 1d 80 e0 4f 24 14 88 1e c0 d0 c0 20 1d 80 e0 83 ec 14 88 1e c0") (Convert-Hex "28 7f 2e 7f 18 84 60 01 b8 10 00 02 68 06 14 88 fe 00 43 e7 14 88 f0 00 fe 00 4f ef 80 e0 00 00 14 88 f0 00 fe 00 5d 1e 80 e0 00 00") "统一语言初始化"
    return ,(Finish-Patch $Original $data "e543f5866bbc99ad4697c6dddb931c5a0fa0526fed34c421541ae32fb7f0c785")
}

function Patch-Unlock([byte[]]$Original) {
    [byte[]]$data = $Original.Clone()
    Set-ExactPatch $data 0x2D1C8 (Convert-Hex "4f ec 28 7f 29 7f 2e 7f d0 c0 20 0c 85 e0 a4 d3 d0 c0 20 0b 84 af 00 0c 80 e0 bd 04 66 12 1e c0 d0 c0 20 0c 80 e0 0d 9c 24 c0 f0 00") (Convert-Hex "28 7f 2e 7f 18 84 f0 00 d1 c0 20 0c 81 e1 0d 9c 21 c1 60 06 a0 01 00 17 fe ff fe 1f 14 88 f0 00 fe 05 23 da 2e ef 28 ef 1f ce f0 00") "地区设置"
    $callOriginal = Convert-Hex "d0 c0 20 1c 80 e0 0f 50"
    $callUnlock = Convert-Hex "d0 c0 20 07 80 e0 7f c8"
    Set-ExactPatch $data 0x30FDC8 $callOriginal $callUnlock "普通语言确认入口"
    Set-ExactPatch $data 0x327140 $callOriginal $callUnlock "备用语言确认入口"
    return ,(Finish-Patch $Original $data "1a383ab94db6bcc4b00583ca3d61339b7f39917aeaf8ec3be9c8809b222c9439")
}

function Find-FirmwareDirectory([string]$Root) {
    if ([string]::IsNullOrWhiteSpace($Root)) { throw "固件路径为空，请重新拖入 ZIP 或文件夹" }
    $candidates = @()
    $possible = @()
    if (Test-Path -LiteralPath $Root -PathType Container) { $possible += Get-Item -LiteralPath $Root }
    $possible += Get-ChildItem -Path $Root -Recurse -Filter "ilaunch3" |
        Where-Object { -not $_.PSIsContainer } |
        ForEach-Object { $_.Directory }
    foreach ($directory in ($possible | Sort-Object FullName -Unique)) {
        $complete = $true
        foreach ($name in $OfficialHashes.Keys) {
            if (-not (Test-Path -LiteralPath (Join-Path $directory.FullName $name) -PathType Leaf)) {
                $complete = $false
                break
            }
        }
        if ($complete) { $candidates += $directory }
    }
    if ($candidates.Count -ne 1) { throw "需要且只能找到一套完整的 29 文件官方固件" }
    return $candidates[0].FullName
}

function Get-UniqueOutput([string]$Parent, [string]$Stem) {
    if ([string]::IsNullOrWhiteSpace($Parent)) { throw "输出目录为空，请把固件放在普通文件夹中再重试" }
    $candidate = Join-Path $Parent "$Stem.zip"
    $number = 2
    while (Test-Path -LiteralPath $candidate) {
        $candidate = Join-Path $Parent "${Stem}_${number}.zip"
        $number++
    }
    return $candidate
}

Write-Host @"
   GGGG   X   X  RRRR
  G        X X   R   R
  G  GGG    X    RRRR
  G    G   X X   R  R
   GGGG   X   X  R   R
"@ -ForegroundColor Cyan
Write-Host "Ricoh GXR 1.51 水水固件修改器" -ForegroundColor Cyan
Write-Host "把官方 ZIP 或文件夹拖到本程序上，检查后输入 1 或 2。"
Write-Host "刷写前请备份照片、使用满电电池，并保留官方 GXR 1.51 恢复包。" -ForegroundColor Yellow

$pendingSource = $Source
while ($true) {
    $temporary = $null
    $stage = $null
    try {
    $Source = $pendingSource
    if ([string]::IsNullOrWhiteSpace($Source)) {
        Write-Host "`n请把官方 ZIP 或文件夹拖到窗口，然后按回车。" -ForegroundColor Yellow
        $Source = (Read-Host ">").Trim().Trim('"').Trim("'")
    }
    if ([string]::IsNullOrWhiteSpace($Source)) { throw "没有选择固件 ZIP 或文件夹" }
    $item = Get-Item -LiteralPath $Source
    Write-Host "`n正在导入并检查：$($item.FullName)" -ForegroundColor Cyan
    if ($item.PSIsContainer) {
        $searchRoot = $item.FullName
    } elseif ($item.Extension -ieq ".zip") {
        $temporary = Join-Path ([IO.Path]::GetTempPath()) ("gxr-input-" + [guid]::NewGuid())
        Expand-Archive -Path $item.FullName -DestinationPath $temporary
        $searchRoot = $temporary
    } else {
        throw "请导入 ZIP 或文件夹"
    }

    $firmwareDirectory = Find-FirmwareDirectory $searchRoot
    $files = @{}
    foreach ($entry in $OfficialHashes.GetEnumerator()) {
        $path = Join-Path $firmwareDirectory $entry.Key
        $actual = (Get-FileHash -Path $path -Algorithm SHA256).Hash.ToLower()
        if ($actual -ne $entry.Value) { throw "$($entry.Key) 不是已知的官方 GXR 1.51 文件" }
        $files[$entry.Key] = [IO.File]::ReadAllBytes($path)
    }
    Write-Host "检查通过：已识别全部 29 个官方升级文件。" -ForegroundColor Green

    Write-Host "`n请选择修改模式：" -ForegroundColor Yellow
    Write-Host "  1. 英文替换版：选择 English 后显示简体中文" -ForegroundColor Green
    Write-Host "  2. 完全解锁版：开放全部 11 种语言" -ForegroundColor Cyan
    do { $choice = Read-Host "`n请输入 1 或 2" } while ($choice -notin @("1", "2"))

    if ($choice -eq "1") {
        $patched = Patch-English $files["ilaunch3"]
        $stem = "Ricoh_GXR_1.51_水水固件_英文替换版"
        $mode = "english"
    } else {
        $patched = Patch-Unlock $files["ilaunch3"]
        $stem = "Ricoh_GXR_1.51_水水固件_完全解锁版"
        $mode = "unlock"
    }

    Write-Host "`n正在生成……" -ForegroundColor Yellow
    $outputParent = Split-Path -Path $item.FullName -Parent
    $output = Get-UniqueOutput $outputParent $stem
    $stage = Join-Path ([IO.Path]::GetTempPath()) ("gxr-output-" + [guid]::NewGuid())
    $packageRoot = Join-Path $stage $stem
    $sdRoot = Join-Path $packageRoot "SD_ROOT"
    New-Item -ItemType Directory -Path $sdRoot -Force | Out-Null
    foreach ($name in $OfficialHashes.Keys) {
        $data = if ($name -eq "ilaunch3") { $patched } else { $files[$name] }
        [IO.File]::WriteAllBytes((Join-Path $sdRoot $name), $data)
    }
    $readme = "项目仓库：$RepoUrl`r`n`r`n把 SD_ROOT 里面的 29 个文件复制到 SD 卡根目录。`r`n"
    [IO.File]::WriteAllText((Join-Path $packageRoot "README.txt"), $readme, [Text.UTF8Encoding]::new($false))
    @{ mode = $mode; file_count = 29; modified_files = @("ilaunch3") } |
        ConvertTo-Json | Set-Content -Path (Join-Path $packageRoot "manifest.json") -Encoding UTF8
    Compress-Archive -Path $packageRoot -DestinationPath $output -CompressionLevel Optimal

    Write-Host "`n生成完成：" -ForegroundColor Green
    Write-Host $output -ForegroundColor Green
    Write-Host "`n完整教程和项目仓库："
    Write-Host $RepoUrl -ForegroundColor Cyan
    Write-Host "`n可以继续拖入下一个固件 ZIP 或文件夹。"
    } catch {
        Write-Host "`n错误：$($_.Exception.Message)" -ForegroundColor Red
        Write-Host "请重新拖入固件 ZIP 或文件夹。" -ForegroundColor Yellow
        Write-Host "脚本行号：$($_.InvocationInfo.ScriptLineNumber)" -ForegroundColor DarkGray
    } finally {
        if ($temporary -and (Test-Path -LiteralPath $temporary)) { Remove-Item -LiteralPath $temporary -Recurse -Force }
        if ($stage -and (Test-Path -LiteralPath $stage)) { Remove-Item -LiteralPath $stage -Recurse -Force }
        $pendingSource = ""
    }
}
