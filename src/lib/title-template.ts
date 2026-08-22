export interface TitleTemplateContext {
  app: string;
  workspace: string;
  service: string;
}

export const DEFAULT_WINDOW_TITLE_TEMPLATE = "{app} ~ {workspace}";
export const DEFAULT_TASKBAR_TITLE_TEMPLATE = "{app} ~ {workspace}";

const TITLE_VARIABLES: Record<keyof TitleTemplateContext, RegExp> = {
  app: /\{app\}/g,
  workspace: /\{workspace\}/g,
  service: /\{service\}/g,
};

export function renderTitleTemplate(
  template: string,
  context: TitleTemplateContext,
): string {
  let rendered = template;
  for (const [name, pattern] of Object.entries(TITLE_VARIABLES) as Array<
    [keyof TitleTemplateContext, RegExp]
  >) {
    rendered = rendered.replace(pattern, context[name]);
  }
  return rendered.trim() || context.app;
}
