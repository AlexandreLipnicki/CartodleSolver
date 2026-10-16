// Parse literals with TypeScript's AST. Never execute data files or their imports.
import ts from 'typescript';
import fs from 'node:fs';
import path from 'node:path';
const input = path.resolve(process.argv[2] || 'data');
const output = process.argv[3];
const data = fs.existsSync(path.join(input, 'data')) ? path.join(input, 'data') : fs.existsSync(path.join(input,'cards-database','data')) ? path.join(input,'cards-database','data') : input;
const root = fs.realpathSync(data);
const cache = new Map();
function load(file, stack = new Set()) {
  file = fs.realpathSync(file);
  if (!file.startsWith(root + path.sep)) throw Error('Import outside data: ' + file);
  if (cache.has(file)) return cache.get(file);
  if (stack.has(file)) throw Error('Circular import');
  const next = new Set(stack).add(file);
  const ast = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true);
  if (ast.parseDiagnostics.length) throw Error('Invalid TypeScript syntax');
  const vars = new Map(), imports = new Map(); let exported;
  for (const s of ast.statements) {
    if (ts.isImportDeclaration(s) && s.importClause?.name) imports.set(s.importClause.name.text, s.moduleSpecifier.text);
    if (ts.isVariableStatement(s)) for (const d of s.declarationList.declarations) vars.set(d.name.getText(ast), d.initializer);
    if (ts.isExportAssignment(s)) exported = s.expression;
  }
  function value(n) {
    if (!n) return null;
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) return n.text;
    if (ts.isNumericLiteral(n)) return Number(n.text);
    if (n.kind === ts.SyntaxKind.TrueKeyword) return true;
    if (n.kind === ts.SyntaxKind.FalseKeyword) return false;
    if (n.kind === ts.SyntaxKind.NullKeyword) return null;
    if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.PlusToken) {
      const a=value(n.left), b=value(n.right);
      if (typeof a==='string' && typeof b==='string') return a+b;
      throw Error('Only literal string concatenation is supported');
    }
    if (ts.isArrayLiteralExpression(n)) return n.elements.map(value);
    if (ts.isAsExpression(n) || ts.isSatisfiesExpression(n) || ts.isParenthesizedExpression(n)) return value(n.expression);
    if (ts.isPrefixUnaryExpression(n) && n.operator === ts.SyntaxKind.MinusToken) return -value(n.operand);
    if (ts.isObjectLiteralExpression(n)) {
      const obj = {};
      for (const p of n.properties) {
        if (!ts.isPropertyAssignment(p) && !ts.isShorthandPropertyAssignment(p)) throw Error('Unsupported object property');
        const key = p.name.text;
        if (['__proto__','constructor','prototype'].includes(key)) throw Error('Unsafe key');
        obj[key] = value(ts.isShorthandPropertyAssignment(p) ? p.name : p.initializer);
      } return obj;
    }
    if (ts.isIdentifier(n)) {
      if (n.text === 'undefined') return null;
      if (vars.has(n.text)) return value(vars.get(n.text));
      if (imports.has(n.text)) {
        const target = imports.get(n.text);
        if (!target.startsWith('.')) throw Error('Non-relative import');
        return load(path.resolve(path.dirname(file), target.endsWith('.ts') ? target : target + '.ts'), next);
      }
    }
    throw Error('Unsupported expression: ' + n.getText(ast).slice(0,80));
  }
  const result = value(exported); cache.set(file,result); return result;
}
function walk(dir) { return fs.readdirSync(dir, {withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name)).flatMap(e => e.isDirectory() ? walk(path.join(dir,e.name)) : e.name.endsWith('.ts') ? [path.join(dir,e.name)] : []); }
const result = {cards:[], invalid:[], skipped:0, source: input};
for (const file of walk(root)) {
  try {
    const c = load(file);
    if (!c?.category) { result.skipped++; continue; }
    result.cards.push({ ...c, localId:path.basename(file,'.ts'), source:path.relative(root,file) });
  } catch(e) {result.invalid.push({file:path.relative(root,file),error:e.message});}
}
if (output) fs.writeFileSync(output,JSON.stringify(result)); else process.stdout.write(JSON.stringify(result));
console.error(`TCGdex: ${result.cards.length} cards, ${result.skipped} metadata, ${result.invalid.length} invalid files`);
