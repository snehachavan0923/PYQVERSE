import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Home from '../pages/Home'

describe('Home Page', () => {
    it('renders brand, hero title, lead text, and main CTAs', () => {
        render(<Home />)

        expect(screen.getAllByText('PYQVERSE').length).toBeGreaterThan(0)
        expect(screen.getByRole('heading', { level: 1, name: /prepare smarter/i })).toBeInTheDocument()
        expect(
            screen.getByText(/your academic preparation, powered by insights from previous-year question papers/i),
        ).toBeInTheDocument()

        // Desktop navbar & Hero CTAs
        const getStartedLinks = screen.getAllByRole('link', { name: /get started/i })
        expect(getStartedLinks.length).toBeGreaterThanOrEqual(1)
        expect(getStartedLinks[0]).toHaveAttribute('href', '/register')

        const loginLinks = screen.getAllByRole('link', { name: /login/i })
        expect(loginLinks.length).toBeGreaterThanOrEqual(1)
        expect(loginLinks[0]).toHaveAttribute('href', '/login')
    })

    it('renders features and step cards', () => {
        render(<Home />)

        expect(screen.getByText('PYQ Intelligence')).toBeInTheDocument()
        expect(screen.getByText('Topic Insights')).toBeInTheDocument()
        expect(screen.getByText('Track Progress')).toBeInTheDocument()

        expect(screen.getByText('Access previous-year papers')).toBeInTheDocument()
        expect(screen.getByText('Explore topic insights')).toBeInTheDocument()
        expect(screen.getByText('Prepare strategically')).toBeInTheDocument()
    })

    it('toggles mobile menu open and closed', async () => {
        const user = userEvent.setup()
        render(<Home />)

        const toggle = screen.getByRole('button', { name: /open navigation menu/i })
        expect(toggle).toHaveAttribute('aria-expanded', 'false')
        expect(screen.queryByRole('dialog', { name: /mobile navigation/i })).not.toBeInTheDocument()

        await user.click(toggle)

        expect(screen.getByRole('button', { name: /close navigation menu/i })).toHaveAttribute(
            'aria-expanded',
            'true',
        )
        expect(screen.getByRole('dialog', { name: /mobile navigation/i })).toBeInTheDocument()

        await user.click(screen.getByRole('button', { name: /close navigation menu/i }))
        expect(screen.queryByRole('dialog', { name: /mobile navigation/i })).not.toBeInTheDocument()
    })

    it('closes mobile menu on escape key press', async () => {
        const user = userEvent.setup()
        render(<Home />)

        const toggle = screen.getByRole('button', { name: /open navigation menu/i })
        await user.click(toggle)
        expect(screen.getByRole('dialog', { name: /mobile navigation/i })).toBeInTheDocument()

        fireEvent.keyDown(window, { key: 'Escape' })
        expect(screen.queryByRole('dialog', { name: /mobile navigation/i })).not.toBeInTheDocument()
    })

    it('closes mobile menu when a navigation link inside is clicked', async () => {
        const user = userEvent.setup()
        render(<Home />)

        await user.click(screen.getByRole('button', { name: /open navigation menu/i }))
        const mobileDialog = screen.getByRole('dialog', { name: /mobile navigation/i })
        expect(mobileDialog).toBeInTheDocument()

        const featuresLink = screen.getAllByRole('link', { name: 'Features' }).find((link) =>
            mobileDialog.contains(link),
        )
        expect(featuresLink).toBeDefined()
        await user.click(featuresLink!)

        expect(screen.queryByRole('dialog', { name: /mobile navigation/i })).not.toBeInTheDocument()
    })

    it('renders key highlights and floating badges', () => {
        render(<Home />)

        expect(screen.getByText('5 Years CIE & SEE')).toBeInTheDocument()
        expect(screen.getByText('Syllabus Mapped')).toBeInTheDocument()
        expect(screen.getByText('Topic Frequency')).toBeInTheDocument()
    })
})

