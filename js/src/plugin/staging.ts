// Staged builds: build each section on its own temporary page, then move it onto the target page
// in one change.
//
// Every plugin property change costs time proportional to the number of shapes on the current
// page (`pb bench build`, 2026-10-26: ~15 ms per rectangle on an empty page, ~60 ms on a
// 1400-shape page; the board, the viewport or hiding the board make no difference). Shapes can
// only be created on the current page and there is no cross-page move. A component instance can
// be placed on any page, though: the built section becomes a main component on its temporary
// page, and one instance of it is placed in the target parent and detached (measured: 180 shapes
// in ~150 ms, names and plugin data kept). Deleting the temporary pages deletes the mains.
//
//   stageBegin()               new temporary page, opened; returns its id and the previous page's
//   stageFinish(rootId)        make the built section a component; returns what the transfer needs
//   stageTransfer(items, ...)  open the target page, place + detach one instance per item; id maps
//                              (a failing item is reported and leaves no copy; the others go on)
//   stageCleanup(pageId)       open pageId (default: stay, unless on a temporary page) and delete
//                              every temporary page, also those left by a crashed build
import { byId } from "./state";

const STAGING_MARK = "staging";

/** The file's pages as plugin Page objects. penpotUtils.getPages() returns plain data without
 *  methods, which `openPage` rejects and which has no plugin data or remove(). */
const filePages = (): any[] => (penpot.currentFile && penpot.currentFile.pages) || [];

/** A section built on a temporary page, ready to be placed on the target page. */
export interface StagedSection { component: string; order: string[]; x: number; y: number }

/** Shape ids in pre-order (parent before children, children in layer order). */
const preorder = (shape: Shape, ids: string[] = []): string[] => {
  ids.push(shape.id);
  for (const child of shape.children || []) preorder(child, ids);
  return ids;
};

const isStagingPage = (page: any): boolean => {
  try { return page.getPluginData("pb") === STAGING_MARK; } catch (error) { return false; }
};

export const stageBegin = async (): Promise<{ page: string; previous: string | null }> => {
  const previous = penpot.currentPage ? penpot.currentPage.id : null;
  const page = penpot.createPage();
  page.name = "pb staging (temporary)";
  page.setPluginData("pb", STAGING_MARK);
  await penpot.openPage(page);
  return { page: page.id, previous };
};

export const stageFinish = (rootId: string): StagedSection => {
  const root = byId(rootId);
  if (!root) throw new Error("staged section not found " + rootId);
  const order = preorder(root);
  const component = penpot.library.local.createComponent([root]);
  if (!component) throw new Error("could not make a component of " + root.name);
  return { component: component.id, order, x: root.x, y: root.y };
};

export const stageTransfer = async (items: StagedSection[], pageId: string, parentId: string | null)
  : Promise<{ ids: Record<string, string>; roots: string[]; failed: { component: string; error: string }[] }> => {
  const page = filePages().find((candidate: any) => candidate.id === pageId);
  if (!page) throw new Error("target page not found " + pageId);
  await penpot.openPage(page);
  const parent = parentId ? byId(parentId) : penpot.root;
  if (!parent) throw new Error("parent not found " + parentId);
  const ids: Record<string, string> = {};   // staged shape id -> id of its copy on the target page
  const roots: string[] = [];
  const failed: { component: string; error: string }[] = [];
  for (const item of items) {
    let copy: Shape | null = null;
    try {
      const component = penpot.library.local.components.find((candidate: any) => candidate.id === item.component);
      if (!component) throw new Error("staged component not found " + item.component);
      copy = component.instance() as Shape;
      parent.appendChild(copy);
      copy.x = item.x; copy.y = item.y;
      copy.detach();
      const copied = preorder(copy);
      if (copied.length !== item.order.length) throw new Error(`staged copy has ${copied.length} shapes, expected ${item.order.length}`);
      item.order.forEach((stagedId, i) => { ids[stagedId] = copied[i]; });
      roots.push(copy.id);
    } catch (error: any) {
      if (copy) { try { copy.remove(); } catch (_) { /* already gone */ } }
      failed.push({ component: item.component, error: String((error && error.message) || error) });
    }
  }
  return { ids, roots, failed };
};

export const stageCleanup = async (pageId: string | null): Promise<number> => {
  const pages = filePages();
  const current = penpot.currentPage && pages.find((candidate: any) => candidate.id === penpot.currentPage!.id);
  const target = pages.find((candidate: any) => candidate.id === pageId)
    || (current && !isStagingPage(current) ? current : pages.find((candidate: any) => !isStagingPage(candidate)));
  if (target && (!penpot.currentPage || penpot.currentPage.id !== target.id)) await penpot.openPage(target);
  let removed = 0;
  for (const page of filePages()) {
    if (isStagingPage(page) && (!penpot.currentPage || page.id !== penpot.currentPage.id)) { page.remove(); removed++; }
  }
  return removed;
};
