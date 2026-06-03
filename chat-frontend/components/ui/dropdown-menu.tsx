"use client";

import type { ComponentPropsWithoutRef } from "react";
import { DropdownMenu as DropdownMenuPrimitive } from "radix-ui";
import { CheckIcon } from "lucide-react";
import { cn } from "@/lib/utils";

const DropdownMenu = DropdownMenuPrimitive.Root;
const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger;
const DropdownMenuGroup = DropdownMenuPrimitive.Group;

const DropdownMenuContent = ({
  className,
  sideOffset = 6,
  ...props
}: ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Content>) => (
  <DropdownMenuPrimitive.Portal>
    <DropdownMenuPrimitive.Content
      data-slot="dropdown-menu-content"
      sideOffset={sideOffset}
      className={cn(
        "z-50 min-w-[12rem] overflow-hidden rounded-xl border bg-popover/95 p-1.5 text-popover-foreground shadow-lg backdrop-blur-sm",
        "data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=open]:animate-in",
        "data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=closed]:animate-out",
        "data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2",
        className,
      )}
      {...props}
    />
  </DropdownMenuPrimitive.Portal>
);

const DropdownMenuItem = ({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Item>) => (
  <DropdownMenuPrimitive.Item
    data-slot="dropdown-menu-item"
    className={cn(
      "relative flex w-full cursor-pointer select-none items-start gap-2 rounded-lg px-2.5 py-2 text-sm outline-none",
      "focus:bg-accent focus:text-accent-foreground",
      "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      "[&_svg:not([class*='size-'])]:size-4 [&_svg]:pointer-events-none [&_svg]:shrink-0",
      className,
    )}
    {...props}
  />
);

const DropdownMenuCheckboxItem = ({
  className,
  children,
  checked,
  ...props
}: ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.CheckboxItem>) => (
  <DropdownMenuPrimitive.CheckboxItem
    data-slot="dropdown-menu-checkbox-item"
    checked={checked}
    className={cn(
      "relative flex w-full cursor-pointer select-none items-start gap-2 rounded-lg py-2 ps-3 pe-8 text-sm outline-none",
      "focus:bg-accent focus:text-accent-foreground",
      "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      "[&_svg:not([class*='size-'])]:size-4 [&_svg]:pointer-events-none [&_svg]:shrink-0",
      className,
    )}
    {...props}
  >
    {children}
    <span className="absolute end-2.5 top-2.5 flex size-4 items-center justify-center">
      <DropdownMenuPrimitive.ItemIndicator>
        <CheckIcon className="size-4" />
      </DropdownMenuPrimitive.ItemIndicator>
    </span>
  </DropdownMenuPrimitive.CheckboxItem>
);

const DropdownMenuLabel = ({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Label>) => (
  <DropdownMenuPrimitive.Label
    data-slot="dropdown-menu-label"
    className={cn("px-2.5 py-1.5 text-muted-foreground text-xs", className)}
    {...props}
  />
);

const DropdownMenuSeparator = ({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Separator>) => (
  <DropdownMenuPrimitive.Separator
    data-slot="dropdown-menu-separator"
    className={cn("-mx-1 my-1 h-px bg-border", className)}
    {...props}
  />
);

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuGroup,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
};
