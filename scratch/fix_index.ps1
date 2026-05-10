$path = "index.tsx"
$content = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)

$oldDiv = '<div className={`systems-view animate-in fade-in duration-500 pb-20 ${isDarkTheme ? ''systems-view-dark'' : ''''}`}>'
$newDiv = '<div className="animate-in fade-in duration-500 pb-20 font-mono">'

$content = $content.Replace($oldDiv, $newDiv)

[System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::UTF8)
