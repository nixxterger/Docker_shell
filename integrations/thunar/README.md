# Thunar (XFCE) integration

Thunar stores custom actions in `~/.config/Thunar/uca.xml`, which has no
safe drop-in directory — add the action via the GUI instead:

1. Thunar → *Edit* → *Configure custom actions…* → *+*
2. **Name:** `Docker Konfig`
   **Command:** `~/.local/bin/docker-shell %f`
   **Icon:** `utilities-terminal`
3. Tab *Appearance Conditions*: check **Directories** only.

Alternatively append this block inside `<actions>` in
`~/.config/Thunar/uca.xml` (while Thunar is closed):

```xml
<action>
    <icon>utilities-terminal</icon>
    <name>Docker Konfig</name>
    <command>~/.local/bin/docker-shell %f</command>
    <description>Configure Docker container access for this folder</description>
    <patterns>*</patterns>
    <directories/>
</action>
```
