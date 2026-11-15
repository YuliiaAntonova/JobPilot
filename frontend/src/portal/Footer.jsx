export default function Footer() {
  return (
    <footer className="fixed bottom-0 left-0 right-0 z-20 flex flex-wrap gap-6 bg-slate-900 px-8 py-5 text-lg font-semibold text-white">
      <a className="hover:text-teal-300" href="#accessibility">
        Accessibility
      </a>
      <a className="hover:text-teal-300" href="#terms">
        Terms of use
      </a>
      <a className="hover:text-teal-300" href="#privacy">
        Privacy
      </a>
      <a className="hover:text-teal-300" href="#export">
        Export data
      </a>
    </footer>
  );
}