"""spel-ai-kompisen: FACITSIDAN (docs/spel-ai-kompisen-design.md, docs/spelai-facit.md).

Betrodd kod som fryser, validerar och rättar en AI-agents poolförslag mot
Spelkompisens egen standard. Agenten (sidoprojektet ~/spel-ai-kompisen) kan
läsa men aldrig ändra den här koden eller dess tabeller.

Tabellerna `spelai_*` skapas ENBART av scripts/migrera_spelai.py. Ingen kod här
skapar dem implicit; läsande vägar tål att de saknas.
"""
