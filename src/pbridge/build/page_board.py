"""The top-level "page board" a design is built into (one per project)."""
from __future__ import annotations

from pbridge.connection import Bridge

# find by id, else by name; create (placed right of another board) if asked; resize to the spec
_PAGE_BOARD_JS = """
    let board = DATA.id && pb.byId(DATA.id);
    if (!board) board = pb.find({name: DATA.name, type: 'board'})[0];
    if (!board && DATA.create) {
      board = penpot.createBoard(); board.name = DATA.name; board.fills = pb.paint(DATA.fill); board.clipContent = true;
      let x = 0, y = 0;
      const neighbour = DATA.after && pb.find({name: DATA.after, type: 'board'})[0];
      if (neighbour) { x = neighbour.x + neighbour.width + DATA.gap; y = neighbour.y; }
      else if (DATA.after === '*') {   // right of every top-level board
        for (const other of penpot.root.children) if (other.id !== board.id) x = Math.max(x, other.x + other.width + DATA.gap);
      }
      board.x = x; board.y = y;
    }
    if (board && DATA.width && DATA.height
        && (Math.abs(board.width - DATA.width) > 0.5 || Math.abs(board.height - DATA.height) > 0.5)) {
      board.resize(DATA.width, DATA.height);
    }
    return board ? board.id : null;"""


class PageBoards:
    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.state = bridge.state

    def ensure(self, name: str | None = None, width: float | None = None, height: float | None = None, create: bool = True,
               fill: str = "#FFFFFF", after: str | None = None, gap: int = 200, reuse_stored_id: bool = True) -> str | None:
        """Id of the page board `name` (created/resized as needed); remembered in config.json.

        after: name of a board to place a NEW board to the right of ('*' = right of everything).
        """
        config = self.state.config
        name = name or config.get("page_board_name") or "Page"
        stored_id = config.get("page_board") if reuse_stored_id else None
        board_id = self.bridge.exec(_PAGE_BOARD_JS, data={"id": stored_id, "name": name, "width": width,
                                                          "height": height, "create": create, "fill": fill,
                                                          "after": after, "gap": gap})
        if board_id:
            config["page_board"] = board_id; config["page_board_name"] = name
            self.state.save_config()
        return board_id
