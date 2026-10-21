// Contract test. Jest strips types, so this runs the TypeScript compiler over the project (as
// tsc --noEmit does) and fails on any error in the contract samples or the client.
const path = require('path');
const ts = require('typescript');

const appRoot = path.join(__dirname, '..');
const checked = ['__tests__/contract/samples.ts', 'src/api/client.ts'].map(f =>
  path.join(appRoot, f),
);

test('contract samples type-check against the generated client types', () => {
  const configPath = path.join(appRoot, 'tsconfig.json');
  const config = ts.readConfigFile(configPath, ts.sys.readFile);
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, appRoot);
  const program = ts.createProgram(parsed.fileNames, {
    ...parsed.options,
    noEmit: true,
  });
  const errors = checked.flatMap(file =>
    ts
      .getPreEmitDiagnostics(program, program.getSourceFile(file))
      .map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')),
  );
  expect(checked.every(file => program.getSourceFile(file))).toBe(true);
  expect(errors).toEqual([]);
}, 120_000);
