import os
import glob
skills_dir = "/Users/JonCorral/Documents/Abbie/.agents/skills/"
out = []
for file in glob.glob(skills_dir + "*/*/SKILL.md") + glob.glob(skills_dir + "*/SKILL.md"):
    with open(file) as f:
        content = f.read()
        out.append(f"--- {file} ---\n{content}\n")
with open("/Users/JonCorral/Documents/Abbie/configs/all_skills.txt", "w") as f:
    f.write("".join(out))
