import { RefObject, useEffect, useRef } from "react";

/** Keep keyboard focus in the active dialog and restore it on close. */
export function useModalFocus(
  open: boolean,
  root: RefObject<HTMLElement>,
  onClose: () => void,
) {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!open || !root.current) return;
    const previous = document.activeElement as HTMLElement | null;
    const element = root.current;
    const controls = () =>
      Array.from(
        element.querySelectorAll<HTMLElement>(
          "button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),a[href]",
        ),
      ).filter((e) => e.offsetParent !== null);
    (controls()[0] || element).focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        close.current();
      }
      if (event.key === "Tab") {
        const list = controls(),
          first = list[0],
          last = list[list.length - 1];
        if (!first) {
          event.preventDefault();
          element.focus();
          return;
        }
        if (
          event.shiftKey &&
          (document.activeElement === first ||
            document.activeElement === element)
        ) {
          event.preventDefault();
          last.focus();
        }
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    element.addEventListener("keydown", key);
    return () => {
      element.removeEventListener("keydown", key);
      if (previous?.isConnected) previous.focus();
    };
  }, [open, root]);
}
