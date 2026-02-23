import { Project } from "ts-morph";
import fs from "fs";
import path from "path";

const project = new Project();
const sourceFile = project.addSourceFileAtPath("index.tsx");

const structure = {
  "src/utils/helpers.ts": [
    "DEFAULT_APP_SETTINGS", "getDaysInMonth", "isWorkDay", "callScrapeSipac", 
    "getMonthWorkDays", "normalizeStatus", "formatWhatsAppText", 
    "formatInlineWhatsAppText", "detectAreaFromTitle"
  ],
  "src/components/ui/UIComponents.tsx": [
    "ToastContainer", "FilterChip", "PgcMiniTaskCard", "PgcAuditRow", 
    "RowCard", "WysiwygEditor", "NotificationCenter"
  ],
  "src/components/modals/Modals.tsx": [
    "HermesModal", "SettingsModal", "DailyHabitsModal", 
    "TaskCreateModal", "TaskEditModal"
  ],
  "src/views/Views.tsx": [
    "DayView", "CalendarView", "CategoryView", "TaskExecutionView"
  ]
};

// 1. Cria os diretórios
Object.keys(structure).forEach(filePath => {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
});

// 2. Extrai como texto e move
for (const [filePath, declarations] of Object.entries(structure)) {
  const newFile = project.createSourceFile(filePath, "", { overwrite: true });
  
  // Adiciona imports básicos
  newFile.addStatements(`import React, { useState, useEffect, useMemo, useRef } from 'react';\n`);

  declarations.forEach(name => {
    // Busca a declaração da variável ou função
    const varDecl = sourceFile.getVariableDeclaration(name);
    const funcDecl = sourceFile.getFunction(name);
    
    if (varDecl) {
      const varStatement = varDecl.getVariableStatement();
      if (varStatement) {
        let text = varStatement.getText();
        if (!varStatement.isExported()) text = "export " + text;
        
        newFile.addStatements(text + "\n");
        varStatement.remove();
      }
    } else if (funcDecl) {
      let text = funcDecl.getText();
      if (!funcDecl.isExported()) text = "export " + text;
      
      newFile.addStatements(text + "\n");
      funcDecl.remove(); 
    } else {
      console.warn(`Aviso: '${name}' não encontrado no index.tsx.`);
    }
  });

  newFile.saveSync();
  console.log(`✅ Criado: ${filePath}`);
}

// 3. Salva o arquivo original
sourceFile.saveSync();
console.log("✅ index.tsx atualizado com as remoções!");