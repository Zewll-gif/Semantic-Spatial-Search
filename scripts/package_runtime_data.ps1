param(
    [switch]$ForceReplace
)

$ErrorActionPreference = 'Stop'
$appRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

$items = @(
    @{ Class='A'; Required=$true;  Source='D:\499_2\499_Thesis_Final_PUBLISH\03_SHARED_DATA\PLANETSCOPE_METADATA\planetscope_full_aoi_rgbn.tif'; Destination='data\rasters\planetscope\planetscope_full_aoi_rgbn.tif' },
    @{ Class='A'; Required=$true;  Source='D:\499_2\499_Thesis_Final_PUBLISH\01_MODEL\06_FULL_AOI_DEPLOYMENT\full_aoi\mosaic\A7_RGBN_REVISED7_TVERSKY_FULL_AOI.tif'; Destination='data\rasters\a7t\A7_RGBN_REVISED7_TVERSKY_FULL_AOI.tif' },
    @{ Class='A'; Required=$true;  Source='D:\499_2\499_Thesis_Final_PUBLISH\03_SHARED_DATA\SPECTRAL_INDICES\NDVI_FULL_AOI.tif'; Destination='data\rasters\indices\NDVI_FULL_AOI.tif' },
    @{ Class='A'; Required=$true;  Source='D:\499_2\499_Thesis_Final_PUBLISH\03_SHARED_DATA\SPECTRAL_INDICES\NDVI_FULL_AOI_METADATA.json'; Destination='data\rasters\indices\NDVI_FULL_AOI_METADATA.json' },
    @{ Class='A'; Required=$true;  Source='D:\499_2\499_Thesis_Final_PUBLISH\03_SHARED_DATA\SPECTRAL_INDICES\NDVI_FULL_AOI_PREVIEW.png'; Destination='data\rasters\indices\NDVI_FULL_AOI_PREVIEW.png' },
    @{ Class='A'; Required=$true;  Source='D:\499_2\499_Thesis_Final_PUBLISH\03_SHARED_DATA\SPECTRAL_INDICES\NDWI_FULL_AOI.tif'; Destination='data\rasters\indices\NDWI_FULL_AOI.tif' },
    @{ Class='A'; Required=$true;  Source='D:\499_2\499_Thesis_Final_PUBLISH\03_SHARED_DATA\SPECTRAL_INDICES\NDWI_FULL_AOI_METADATA.json'; Destination='data\rasters\indices\NDWI_FULL_AOI_METADATA.json' },
    @{ Class='A'; Required=$true;  Source='D:\499_2\499_Thesis_Final_PUBLISH\03_SHARED_DATA\SPECTRAL_INDICES\NDWI_FULL_AOI_PREVIEW.png'; Destination='data\rasters\indices\NDWI_FULL_AOI_PREVIEW.png' },
    @{ Class='A'; Required=$true;  Source='D:\499_2\499_Thesis_Final_PUBLISH\03_SHARED_DATA\DEM\geoai_aoi_dem_cop30_30m.tif'; Destination='data\rasters\dem\geoai_aoi_dem_cop30_30m.tif' },
    @{ Class='B'; Required=$false; Source='D:\499_2\499_Thesis_Final_PUBLISH\01_MODEL\06_FULL_AOI_DEPLOYMENT\vector\vector_clean\A7_T_FULL_AOI_POLYGONS_CLEAN.gpkg'; Destination='data\vectors\A7_T_FULL_AOI_POLYGONS_CLEAN.gpkg' },
    @{ Class='A'; Required=$true;  Source='D:\499_2\499_Thesis_Final_PUBLISH\03_SHARED_DATA\FINAL_CLASS_PALETTE\revised7_palette.json'; Destination='data\metadata\palette\revised7_palette.json' },
    @{ Class='B'; Required=$false; Source='D:\499_2\499_Thesis_Final_PUBLISH\01_MODEL\06_FULL_AOI_DEPLOYMENT\qa\A7_T_EVIDENCE_CROSSCHECK_AUDIT.json'; Destination='data\metadata\evidence\A7_T_EVIDENCE_CROSSCHECK_AUDIT.json' },
    @{ Class='B'; Required=$false; Source='D:\499_2\499_Thesis_Final_PUBLISH\01_MODEL\06_FULL_AOI_DEPLOYMENT\qa\EVIDENCE_CROSSCHECK_A7T\class_spectral_profiles.csv'; Destination='data\metadata\evidence\class_spectral_profiles.csv' },
    @{ Class='B'; Required=$false; Source='D:\499_2\499_Thesis_Final_PUBLISH\01_MODEL\06_FULL_AOI_DEPLOYMENT\qa\EVIDENCE_CROSSCHECK_A7T\class_spectral_profiles.json'; Destination='data\metadata\evidence\class_spectral_profiles.json' },
    @{ Class='B'; Required=$false; Source='D:\499_2\499_Thesis_Final_PUBLISH\03_SHARED_DATA\EXTERNAL_LULC_REFERENCE\harmonized\A7T_HARMONIZED_10M.tif'; Destination='data\metadata\external_lulc\harmonized\A7T_HARMONIZED_10M.tif' },
    @{ Class='B'; Required=$false; Source='D:\499_2\499_Thesis_Final_PUBLISH\03_SHARED_DATA\EXTERNAL_LULC_REFERENCE\harmonized\GISTDA_HARMONIZED_10M.tif'; Destination='data\metadata\external_lulc\harmonized\GISTDA_HARMONIZED_10M.tif' },
    @{ Class='B'; Required=$false; Source='D:\499_2\499_Thesis_Final_PUBLISH\03_SHARED_DATA\EXTERNAL_LULC_REFERENCE\metadata\comparison_metadata.json'; Destination='data\metadata\external_lulc\metadata\comparison_metadata.json' },
    @{ Class='B'; Required=$false; Source='D:\499_4\FINAL_MODEL_FREEZE\A7_RGBN_REVISED7_TVERSKY\training_config.json'; Destination='data\metadata\model\training_config.json' },
    @{ Class='B'; Required=$false; Source='D:\499_4\FINAL_MODEL_FREEZE\A7_RGBN_REVISED7_TVERSKY\metrics.json'; Destination='data\metadata\model\metrics.json' },
    @{ Class='B'; Required=$false; Source='D:\499_4\FINAL_MODEL_FREEZE\A7_RGBN_REVISED7_TVERSKY\README.txt'; Destination='data\metadata\model\README.txt' },
    @{ Class='A'; Required=$true;  Source=(Join-Path $appRoot 'backend\knowledge\knowledge_base.json'); Destination='data\knowledge\knowledge_base.json' },
    @{ Class='B'; Required=$false; Source=(Join-Path $appRoot 'data\project_rag_index.json'); Destination='data\knowledge\project_rag_index.json' },
    @{ Class='A'; Required=$true;  Source=(Join-Path $appRoot 'data\human_corrections.sqlite'); Destination='data\corrections\human_corrections.sqlite' }
)

$directoryItems = @(
    @{ Class='A'; Required=$true;  Source='D:\499_2\499_Thesis_Final_PUBLISH\01_MODEL\06_FULL_AOI_DEPLOYMENT\full_aoi\tiles_rgb'; Destination='data\runtime\full_aoi\tiles_rgb' },
    @{ Class='B'; Required=$false; Source='D:\499_2\499_Thesis_Final_PUBLISH\01_MODEL\06_FULL_AOI_DEPLOYMENT\full_aoi\tiles_geotiff'; Destination='data\runtime\full_aoi\tiles_geotiff' },
    @{ Class='B'; Required=$false; Source='D:\499_2\499_Thesis_Final_PUBLISH\01_MODEL\06_FULL_AOI_DEPLOYMENT\full_aoi\semantic_search'; Destination='data\runtime\full_aoi\semantic_search' }
)

foreach ($group in $directoryItems) {
    if (-not (Test-Path -LiteralPath $group.Source -PathType Container)) {
        throw "Missing source directory: $($group.Source)"
    }
    foreach ($file in Get-ChildItem -LiteralPath $group.Source -Recurse -File) {
        $relative = $file.FullName.Substring($group.Source.Length).TrimStart('\')
        $items += @{
            Class=$group.Class
            Required=$group.Required
            Source=$file.FullName
            Destination=(Join-Path $group.Destination $relative)
        }
    }
}

$manifest = @()
foreach ($item in $items) {
    $source = [IO.Path]::GetFullPath($item.Source)
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Missing source file: $source"
    }
    $destination = [IO.Path]::GetFullPath((Join-Path $appRoot $item.Destination))
    $destinationDirectory = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null

    $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    if (Test-Path -LiteralPath $destination) {
        $existingHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
        if ($existingHash -ne $sourceHash -and -not $ForceReplace) {
            throw "Destination differs; rerun with -ForceReplace only after review: $destination"
        }
    }
    if (-not (Test-Path -LiteralPath $destination) -or $ForceReplace) {
        Copy-Item -LiteralPath $source -Destination $destination -Force:$ForceReplace
    }
    $destinationHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
    if ($sourceHash -ne $destinationHash) {
        throw "SHA-256 mismatch after copy: $destination"
    }
    $manifest += [ordered]@{
        classification = $item.Class
        runtime_required = [bool]$item.Required
        source = $source
        destination = $item.Destination.Replace('\', '/')
        size_bytes = (Get-Item -LiteralPath $destination).Length
        sha256 = $destinationHash
        verified = $true
    }
}

New-Item -ItemType Directory -Path (Join-Path $appRoot 'cache\sentinel2') -Force | Out-Null
$manifestPath = Join-Path $appRoot 'data\metadata\runtime_data_manifest.json'
$payload = [ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    app_root = $appRoot
    source_files_preserved = $true
    item_count = $manifest.Count
    items = $manifest
}
$payload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Host "Copied and SHA-256 verified $($manifest.Count) runtime files."
Write-Host "Manifest: $manifestPath"
