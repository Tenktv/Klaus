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
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\einrichten.ps1"" -Ordner ""{app}"" {code:UpdateSchalter} {code:OllamaSchalter}"; StatusMsg: "Richte Klaus ein (Python und Pakete) ..."; Flags: waituntilterminated
Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\src\klaus_app.py"""; WorkingDir: "{app}"; Description: "Klaus jetzt starten"; Flags: nowait postinstall

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Get-CimInstance Win32_Process | ? CommandLine -like '*klaus_app.py*' | % {{ Stop-Process -Id $_.ProcessId -Force }"""; Flags: runhidden; RunOnceId: "KlausBeenden"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"

[Code]
var
  NamenSeite: TInputQueryWizardPage;
  SchluesselSeite: TInputQueryWizardPage;
  EigeneKiSeite: TInputQueryWizardPage;
  LokalSeite: TInputOptionWizardPage;
  UpdateSeite: TInputQueryWizardPage;
  StreamSeite: TInputQueryWizardPage;

const
  OLLAMA_MODELL = 'qwen2.5:7b-instruct-q4_K_M';

function IstUpdate(): Boolean;
begin
  Result := ExpandConstant('{param:UPDATE|0}') <> '0';
end;

function UpdateSchalter(Param: String): String;
begin
  if IstUpdate() then Result := '-Update' else Result := '';
end;

function OllamaSchalter(Param: String): String;
begin
  Result := '';
  if (not IstUpdate()) and LokalSeite.Values[0] then Result := '-Ollama -OllamaModell ' + OLLAMA_MODELL;
end;

procedure InitializeWizard();
begin
  NamenSeite := CreateInputQueryPage(wpSelectDir, 'Dein Assistent', 'Wie soll er heißen, und wie heißt du?',
    'Auf den Namen des Assistenten hört er auch als Weckwort („Klaus, wie wird das Wetter?“). Beides kannst du später in der .env ändern.');
  NamenSeite.Add('Name des Assistenten:', False);
  NamenSeite.Add('Dein Name (so spricht er dich an):', False);
  NamenSeite.Values[0] := 'Klaus';
  NamenSeite.Values[1] := GetUserNameString();

  SchluesselSeite := CreateInputQueryPage(NamenSeite.ID, 'KI-Schlüssel', 'Womit soll dein Assistent denken? (alles optional, mindestens eins empfohlen)',
    'Du nutzt deine eigenen Konten. Gemini (aistudio.google.com/apikey, kostenlos) = natürliche Sprachgespräche. ' +
    'Groq (console.groq.com/keys, kostenlos) und OpenRouter (openrouter.ai/keys, Gratis-Modelle) = Ersatz, wenn Gemini ausfällt, ' +
    'und Antworten ohne Gemini. Fish Audio (fish.audio → API) = eigene Stimmen und Figuren-Stimmen. Alles auch später im Startmenü unter „Einstellungen“.');
  SchluesselSeite.Add('Gemini API-Schlüssel:', False);
  SchluesselSeite.Add('Groq API-Schlüssel:', False);
  SchluesselSeite.Add('OpenRouter API-Schlüssel:', False);
  SchluesselSeite.Add('Fish Audio API-Schlüssel:', False);

  EigeneKiSeite := CreateInputQueryPage(SchluesselSeite.ID, 'Eigener KI-Anbieter (optional)', 'OpenAI, Mistral, DeepSeek, LM Studio … – alles im OpenAI-Format',
    'Adresse der API, z. B. https://api.openai.com/v1 oder für LM Studio http://localhost:1234/v1. Leer lassen, wenn du keinen weiteren Anbieter willst.');
  EigeneKiSeite.Add('API-Adresse:', False);
  EigeneKiSeite.Add('API-Schlüssel (bei LM Studio leer lassen):', False);
  EigeneKiSeite.Add('Modell(e), kommagetrennt (z. B. gpt-4o-mini):', False);

  LokalSeite := CreateInputOptionPage(EigeneKiSeite.ID, 'Lokale KI (optional)', 'Ganz ohne Internet und ohne Konto denken',
    'Installiert Ollama und das Modell ' + OLLAMA_MODELL + ' (ca. 5 GB). Läuft am besten mit einer Grafikkarte ab 8 GB. ' +
    'Der Assistent nutzt die lokale KI, wenn keine Cloud-KI antwortet.', False, False);
  LokalSeite.Add('Ollama und das lokale Modell installieren');

  StreamSeite := CreateInputQueryPage(LokalSeite.ID, 'Streaming (optional)', 'Soll dein Assistent deinen Chat mitlesen?',
    'Mit deinem Twitch-Kanalnamen liest er den Chat mit, begrüßt neue Leute und liest vor. YouTube, X, Instagram, Discord ' +
    'und andere Plattformen verbindest du später selbst: Taskleisten-Symbol → „Verbindungen“ oder sag „verbinde YouTube“.');
  StreamSeite.Add('Twitch-Kanalname (z. B. deinkanal):', False);

  UpdateSeite := CreateInputQueryPage(StreamSeite.ID, 'Automatische Updates (Testphase)', 'Neue Versionen kommen von GitHub',
    'Solange Klaus nur getestet wird, liegen die Updates in einem privaten GitHub-Repo. Trag hier den Update-Token ein, ' +
    'den du von Nikola bekommen hast (nur Lesezugriff). Hast du keinen, leer lassen – nachtragen geht später in den Einstellungen (.env).');
  UpdateSeite.Add('Update-Token:', True);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = LokalSeite.ID) and (not LokalSeite.Values[0]) and (Trim(SchluesselSeite.Values[0]) = '') and
     (Trim(SchluesselSeite.Values[1]) = '') and (Trim(SchluesselSeite.Values[2]) = '') and (Trim(EigeneKiSeite.Values[0]) = '') then
    Result := MsgBox('Ohne KI-Schlüssel und ohne lokale KI kann dein Assistent nicht antworten. ' +
                     'Du kannst Schlüssel später im Startmenü unter „Einstellungen“ eintragen. Trotzdem weiter?', mbConfirmation, MB_YESNO) = IDYES;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := IstUpdate() and ((PageID = NamenSeite.ID) or (PageID = SchluesselSeite.ID) or (PageID = EigeneKiSeite.ID) or
                             (PageID = LokalSeite.ID) or (PageID = StreamSeite.ID) or (PageID = UpdateSeite.ID));
end;

function Bereinigt(Wert: String): String;
begin
  Result := Trim(Wert);
  StringChangeEx(Result, #13, '', True);
  StringChangeEx(Result, #10, '', True);
end;

procedure EnvSchreiben();
var
  Datei, Name, EigenKey, Kanal: String;
  Zeilen: TArrayOfString;
begin
  Datei := ExpandConstant('{app}\.env');
  if FileExists(Datei) then Exit;   { bestehende Einstellungen nie ueberschreiben }
  Name := Bereinigt(NamenSeite.Values[0]);
  if Name = '' then Name := 'Klaus';
  EigenKey := Bereinigt(EigeneKiSeite.Values[1]);
  if (EigenKey = '') and (Bereinigt(EigeneKiSeite.Values[0]) <> '') then EigenKey := 'lokal';   { LM Studio & Co. brauchen keinen }
  Kanal := Lowercase(Bereinigt(StreamSeite.Values[0]));
  StringChangeEx(Kanal, 'https://', '', True);
  StringChangeEx(Kanal, 'www.', '', True);
  StringChangeEx(Kanal, 'twitch.tv/', '', True);
  StringChangeEx(Kanal, '@', '', True);
  StringChangeEx(Kanal, '/', '', True);
  SetArrayLength(Zeilen, 14);
  Zeilen[0] := '# Klaus - Einstellungen (vom Installer angelegt). Vorlage mit allen Optionen: .env.example';
  Zeilen[1] := 'KLAUS_NAME=' + Name;
  Zeilen[2] := 'KLAUS_NUTZER=' + Bereinigt(NamenSeite.Values[1]);
  Zeilen[3] := 'GEMINI_API_KEY=' + Bereinigt(SchluesselSeite.Values[0]);
  Zeilen[4] := 'GROQ_API_KEY=' + Bereinigt(SchluesselSeite.Values[1]);
  Zeilen[5] := 'OPENROUTER_API_KEY=' + Bereinigt(SchluesselSeite.Values[2]);
  Zeilen[6] := 'FISH_API_KEY=' + Bereinigt(SchluesselSeite.Values[3]);
  Zeilen[7] := 'ERSATZ_KI_URL=' + Bereinigt(EigeneKiSeite.Values[0]);
  Zeilen[8] := 'ERSATZ_KI_KEY=' + EigenKey;
  Zeilen[9] := 'ERSATZ_KI_MODELLE=' + Bereinigt(EigeneKiSeite.Values[2]);
  Zeilen[10] := 'OLLAMA_MODEL=' + OLLAMA_MODELL;
  Zeilen[11] := 'KLAUS_AUTO_UPDATE=1';
  Zeilen[12] := 'KLAUS_UPDATE_TOKEN=' + Bereinigt(UpdateSeite.Values[0]);
  Zeilen[13] := 'TWITCH_KANAL=' + Kanal;
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
