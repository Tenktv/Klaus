; Klaus - Windows-Installer (Inno Setup 6). Gebaut von .github/workflows/installer.yml:
;   ISCC /DAppVersion=1.0.0 /DQuelle=..\build\klaus installer\klaus.iss   ->  installer\Output\Klaus-Setup.exe
; Installiert ohne Admin-Rechte nach %LOCALAPPDATA%\Programs\Klaus. Updates: dieselbe Setup.exe still
; (/VERYSILENT /UPDATE) - .env, data\ und eigene Stimmen bleiben erhalten.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Quelle
  #define Quelle "..\build\klaus"
#endif

[Setup]
AppId={{7B1E6C2A-4F0D-4C5B-9C1E-3A5D2F8B9E01}
AppName=Klaus
AppVersion={#AppVersion}
AppPublisher=Klesro Web
DefaultDirName={localappdata}\Programs\Klaus
DefaultGroupName=Klaus
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=Klaus-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Klaus (Sprach-Assistent)
CloseApplications=no

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktop"; Description: "Verknüpfung auf dem Desktop"; Flags: unchecked

[Files]
Source: "{#Quelle}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: ".env"

[Dirs]
Name: "{app}\data"
Name: "{app}\data\stimmen\eigene"

[Icons]
Name: "{group}\Klaus"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\src\klaus_app.py"""; WorkingDir: "{app}"
Name: "{group}\Eigene Stimmen (Sprachproben hier ablegen)"; Filename: "{app}\data\stimmen\eigene"
Name: "{group}\Einstellungen (.env)"; Filename: "notepad.exe"; Parameters: """{app}\.env"""
Name: "{group}\Klaus deinstallieren"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Klaus"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\src\klaus_app.py"""; WorkingDir: "{app}"; Tasks: desktop

[Run]
; Python, Pakete, Stimme - beim ersten Mal ein paar Minuten (Fenster zeigt den Fortschritt), bei Updates nur, was sich geaendert hat
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\einrichten.ps1"" -Ordner ""{app}"" {code:UpdateSchalter}"; StatusMsg: "Richte Klaus ein (Python und Pakete) ..."; Flags: waituntilterminated
Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\src\klaus_app.py"""; WorkingDir: "{app}"; Description: "Klaus jetzt starten"; Flags: nowait postinstall

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Get-CimInstance Win32_Process | ? CommandLine -like '*klaus_app.py*' | % {{ Stop-Process -Id $_.ProcessId -Force }"""; Flags: runhidden; RunOnceId: "KlausBeenden"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"

[Code]
var
  NamenSeite: TInputQueryWizardPage;
  SchluesselSeite: TInputQueryWizardPage;

function IstUpdate(): Boolean;
begin
  Result := ExpandConstant('{param:UPDATE|0}') <> '0';
end;

function UpdateSchalter(Param: String): String;
begin
  if IstUpdate() then Result := '-Update' else Result := '';
end;

procedure InitializeWizard();
begin
  NamenSeite := CreateInputQueryPage(wpSelectDir, 'Dein Assistent', 'Wie soll er heißen, und wie heißt du?',
    'Auf den Namen des Assistenten hört er auch als Weckwort („Klaus, wie wird das Wetter?“). Beides kannst du später in der .env ändern.');
  NamenSeite.Add('Name des Assistenten:', False);
  NamenSeite.Add('Dein Name (so spricht er dich an):', False);
  NamenSeite.Values[0] := 'Klaus';
  NamenSeite.Values[1] := GetUserNameString();

  SchluesselSeite := CreateInputQueryPage(NamenSeite.ID, 'Schlüssel (optional)', 'Für Gespräche und besondere Stimmen',
    'Gemini-Schlüssel (kostenlos: aistudio.google.com/apikey) für natürliche Gespräche. Fish-Audio-Schlüssel (fish.audio → API) für eigene Stimmen und Figuren-Stimmen. Beides geht auch später.');
  SchluesselSeite.Add('Gemini API-Schlüssel:', False);
  SchluesselSeite.Add('Fish Audio API-Schlüssel:', False);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := IstUpdate() and ((PageID = NamenSeite.ID) or (PageID = SchluesselSeite.ID));
end;

function Bereinigt(Wert: String): String;
begin
  Result := Trim(Wert);
  StringChangeEx(Result, #13, '', True);
  StringChangeEx(Result, #10, '', True);
end;

procedure EnvSchreiben();
var
  Datei, Name: String;
  Zeilen: TArrayOfString;
begin
  Datei := ExpandConstant('{app}\.env');
  if FileExists(Datei) then Exit;   { bestehende Einstellungen nie ueberschreiben }
  Name := Bereinigt(NamenSeite.Values[0]);
  if Name = '' then Name := 'Klaus';
  SetArrayLength(Zeilen, 6);
  Zeilen[0] := '# Klaus - Einstellungen (vom Installer angelegt). Vorlage mit allen Optionen: .env.example';
  Zeilen[1] := 'KLAUS_NAME=' + Name;
  Zeilen[2] := 'KLAUS_NUTZER=' + Bereinigt(NamenSeite.Values[1]);
  Zeilen[3] := 'GEMINI_API_KEY=' + Bereinigt(SchluesselSeite.Values[0]);
  Zeilen[4] := 'FISH_API_KEY=' + Bereinigt(SchluesselSeite.Values[1]);
  Zeilen[5] := 'KLAUS_AUTO_UPDATE=1';
  SaveStringsToUTF8File(Datei, Zeilen, False);   { erste Zeile ist ein Kommentar - ein BOM davor stoert nicht }
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Ergebnis: Integer;
begin
  { laufenden Klaus beenden, damit Dateien ersetzt werden koennen }
  Exec('powershell.exe', '-NoProfile -Command "Get-CimInstance Win32_Process | ? CommandLine -like ''*klaus_app.py*'' | % { Stop-Process -Id $_.ProcessId -Force }"',
       '', SW_HIDE, ewWaitUntilTerminated, Ergebnis);
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then EnvSchreiben();
end;
